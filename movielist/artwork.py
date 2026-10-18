"""Safe, on-demand artwork resolution with a local disk cache.

Flow: a page requests artwork for a Kodi media id -> the art table is
queried for candidate URLs -> candidates are resolved through explicit
security controls (configured path mappings, allowed directories, host
allowlist, private-address rejection) -> the image is cached locally
and served.  Failures are negative-cached so broken artwork is not
re-fetched on every page view.  A placeholder image is returned when
nothing can be resolved.

This component never writes to the Kodi database or media directories.
"""

from __future__ import annotations

import hashlib
import io
import ipaddress
import logging
import os
import socket
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

import httpx
from PIL import Image, UnidentifiedImageError

from .config import Settings
from .kodi import KodiRepository

log = logging.getLogger(__name__)

MEDIA_TYPES = frozenset({"movie", "tvshow", "season", "episode"})
ART_TYPES = frozenset(
    {"poster", "fanart", "banner", "thumb", "landscape", "clearlogo"}
)

_ALLOWED_IMAGE_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png",
                          "GIF": "image/gif", "WEBP": "image/webp"}
_ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

_MAX_REDIRECTS = 5


class ArtworkError(Exception):
    """Base class for artwork resolution failures."""


class UnsafeArtworkSource(ArtworkError):
    """The artwork source failed a security check."""


@dataclass
class ArtworkResult:
    path: Path
    content_type: str
    etag: str


Fetcher = Callable[[str], bytes]


def _check_remote_url(parts, approved_hosts: frozenset[str]) -> None:
    if parts.scheme not in ("http", "https"):
        raise UnsafeArtworkSource(f"Scheme not allowed: {parts.scheme!r}")
    if not parts.hostname:
        raise UnsafeArtworkSource("URL has no host")
    host = parts.hostname.lower().rstrip(".")
    if host not in approved_hosts:
        raise UnsafeArtworkSource(f"Host not in allowlist: {host!r}")


def _check_remote_address(host: str, port: int | None) -> None:
    """Reject hosts that resolve to private, loopback or link-local IPs."""
    try:
        infos = socket.getaddrinfo(host, port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ArtworkError(f"DNS resolution failed for {host!r}") from exc
    if not infos:
        raise ArtworkError(f"No addresses for {host!r}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise UnsafeArtworkSource(
                f"Host {host!r} resolves to a non-public address"
            )


def _fetch_remote(
    url: str, settings: Settings, client: httpx.Client
) -> bytes:
    """Fetch a remote artwork URL with full validation per hop."""
    current = url
    for _ in range(_MAX_REDIRECTS + 1):
        parts = urlsplit(current)
        _check_remote_url(parts, settings.approved_artwork_hosts)
        _check_remote_address(parts.hostname, parts.port)
        with client.stream("GET", current) as response:
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if not location:
                    raise ArtworkError("Redirect without location")
                current = str(httpx.URL(current).join(location))
                continue
            if response.status_code != 200:
                raise ArtworkError(
                    f"HTTP {response.status_code} fetching artwork"
                )
            content_type = (
                response.headers.get("content-type") or ""
            ).split(";")[0].strip().lower()
            if not content_type.startswith("image/"):
                raise ArtworkError(
                    f"Unexpected content type: {content_type!r}"
                )
            declared = response.headers.get("content-length")
            if declared and declared.isdigit():
                if int(declared) > settings.artwork_max_bytes:
                    raise ArtworkError("Artwork exceeds size limit")
            chunks: list[bytes] = []
            received = 0
            for chunk in response.iter_bytes():
                received += len(chunk)
                if received > settings.artwork_max_bytes:
                    raise ArtworkError("Artwork exceeds size limit")
                chunks.append(chunk)
            data = b"".join(chunks)
            if not data:
                raise ArtworkError("Empty artwork response")
            return data
    raise ArtworkError("Too many redirects fetching artwork")


def _default_http_fetcher(settings: Settings) -> Fetcher:
    """Fetch a validated remote URL with size and content checks."""

    def fetch(url: str) -> bytes:
        timeout = httpx.Timeout(
            settings.artwork_read_timeout,
            connect=settings.artwork_connect_timeout,
        )
        with httpx.Client(
            timeout=timeout, follow_redirects=False, trust_env=False
        ) as client:
            return _fetch_remote(url, settings, client)

    return fetch


class ArtworkCache:
    """Resolve Kodi artwork references to locally cached image files."""

    def __init__(
        self,
        settings: Settings,
        repo: KodiRepository,
        fetcher: Fetcher | None = None,
        placeholder: Path | None = None,
    ):
        self._settings = settings
        self._repo = repo
        self._fetcher = fetcher or _default_http_fetcher(settings)
        self._cache_dir = Path(settings.artwork_cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._placeholder = placeholder or (
            Path(__file__).resolve().parent.parent / "static" / "no-poster.png"
        )
        self._lock = threading.Lock()
        self._failures: dict[tuple[str, int, str], float] = {}
        # Mapping targets are implicitly allowed local roots.
        self._allowed_roots = [
            Path(p).resolve()
            for p in (
                list(settings.media_path_mappings.values())
                + list(settings.artwork_allowed_dirs)
            )
            if p
        ]

    # -- public API ---------------------------------------------------------

    def get(
        self, media_type: str, media_id: int, art_type: str
    ) -> ArtworkResult:
        """Return cached artwork or resolve, cache and return it.

        Never raises for missing/broken artwork; returns the placeholder.
        """
        if media_type not in MEDIA_TYPES or art_type not in ART_TYPES:
            raise UnsafeArtworkSource("Unsupported artwork request")
        if media_id <= 0:
            raise UnsafeArtworkSource("Invalid media id")

        key = (media_type, media_id, art_type)
        try:
            candidates = self._repo.artwork_urls(media_type, media_id, art_type)
        except Exception:
            log.warning("Artwork lookup failed", exc_info=True)
            candidates = []

        if not self._is_failed(key):
            for url in candidates:
                try:
                    result = self._resolve_and_cache(url)
                    self._clear_failure(key)
                    return result
                except UnsafeArtworkSource as exc:
                    log.warning("Rejected artwork source: %s", exc)
                except ArtworkError as exc:
                    log.info("Artwork fetch failed: %s", exc)
            if candidates:
                self._mark_failed(key)

        return self.placeholder_result()

    def placeholder_result(self) -> ArtworkResult:
        path = self._placeholder
        stat = path.stat() if path.exists() else None
        etag = hashlib.sha256(
            f"{path}:{stat.st_size if stat else 0}:{stat.st_mtime_ns if stat else 0}".encode()
        ).hexdigest()[:16]
        content_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        return ArtworkResult(path=path, content_type=content_type, etag=etag)

    # -- internals ----------------------------------------------------------

    def _cache_path_for(self, url: str, data: bytes) -> tuple[Path, str]:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        suffix = self._detect_suffix(data)
        return self._cache_dir / f"{digest}{suffix}", digest

    def _resolve_and_cache(self, url: str) -> ArtworkResult:
        parts = urlsplit(url)
        if parts.scheme in ("http", "https"):
            data = self._fetcher(url)
        elif parts.scheme == "" and url.startswith("/"):
            data = self._read_local_file(url)
        elif url.lower().startswith("smb://"):
            local = self._map_smb_path(url)
            data = self._read_local_file(local)
        else:
            raise UnsafeArtworkSource(
                f"Unsupported artwork URL scheme: {parts.scheme!r}"
            )

        data = self._validate_image(data)
        path, digest = self._cache_path_for(url, data)
        with self._lock:
            if not path.exists() or path.stat().st_size == 0:
                tmp = path.with_suffix(path.suffix + ".tmp")
                tmp.write_bytes(data)
                os.replace(tmp, path)
                self._evict_if_needed()
        stat = path.stat()
        return ArtworkResult(
            path=path,
            content_type=_ALLOWED_IMAGE_FORMATS[self._image_format(data)],
            etag=f"{digest[:16]}-{stat.st_mtime_ns}",
        )

    def _map_smb_path(self, url: str) -> str:
        # smb://host/share/rest -> configured local root + rest
        rest = url[6:]  # strip "smb://"
        for prefix, target in self._settings.media_path_mappings.items():
            if not prefix.lower().startswith("smb://"):
                continue
            prefix_rest = prefix[6:]
            if rest.lower().startswith(prefix_rest.lower()):
                remainder = rest[len(prefix_rest):].lstrip("/")
                return str(Path(target) / remainder)
        raise UnsafeArtworkSource("SMB path has no configured mapping")

    def _read_local_file(self, path_str: str) -> bytes:
        resolved = Path(path_str).resolve()
        if not self._is_allowed_path(resolved):
            raise UnsafeArtworkSource("Path outside allowed directories")
        if not resolved.is_file():
            raise ArtworkError("Artwork file not found")
        size = resolved.stat().st_size
        if size == 0:
            raise ArtworkError("Artwork file is empty")
        if size > self._settings.artwork_max_bytes:
            raise ArtworkError("Artwork exceeds size limit")
        if resolved.suffix.lower() not in _ALLOWED_SUFFIXES:
            raise UnsafeArtworkSource("File extension not allowed")
        data = resolved.read_bytes()
        if len(data) > self._settings.artwork_max_bytes:
            raise ArtworkError("Artwork exceeds size limit")
        return data

    def _is_allowed_path(self, resolved: Path) -> bool:
        for root in self._allowed_roots:
            try:
                if resolved.is_relative_to(root):
                    return True
            except ValueError:
                continue
        return False

    def _validate_image(self, data: bytes) -> bytes:
        """Validate image format and dimensions."""
        try:
            with Image.open(io.BytesIO(data)) as img:
                fmt = img.format
                width, height = img.size
        except (UnidentifiedImageError, OSError) as exc:
            raise ArtworkError("Response is not a recognized image") from exc
        if fmt not in _ALLOWED_IMAGE_FORMATS:
            raise ArtworkError(f"Unsupported image format: {fmt!r}")
        max_dim = self._settings.artwork_max_dimension
        if not (0 < width <= max_dim and 0 < height <= max_dim):
            raise ArtworkError(
                f"Image dimensions {width}x{height} outside allowed range"
            )
        return data

    @staticmethod
    def _image_format(data: bytes) -> str | None:
        try:
            with Image.open(io.BytesIO(data)) as img:
                fmt = img.format
        except (UnidentifiedImageError, OSError):
            return None
        if fmt not in _ALLOWED_IMAGE_FORMATS:
            return None
        return fmt

    def _detect_suffix(self, data: bytes) -> str:
        fmt = self._image_format(data)
        return {
            "JPEG": ".jpg",
            "PNG": ".png",
            "GIF": ".gif",
            "WEBP": ".webp",
        }.get(fmt, ".img")

    def _is_failed(self, key: tuple[str, int, str]) -> bool:
        expiry = self._failures.get(key)
        if expiry is None:
            return False
        if expiry < time.monotonic():
            self._failures.pop(key, None)
            return False
        return True

    def _mark_failed(self, key: tuple[str, int, str]) -> None:
        self._failures[key] = (
            time.monotonic() + self._settings.artwork_failure_ttl
        )

    def _clear_failure(self, key: tuple[str, int, str]) -> None:
        self._failures.pop(key, None)

    def _evict_if_needed(self) -> None:
        max_size = self._settings.artwork_cache_max_size
        try:
            entries = []
            total = 0
            with os.scandir(self._cache_dir) as it:
                for entry in it:
                    if not entry.is_file() or entry.name.endswith(".tmp"):
                        continue
                    stat = entry.stat()
                    total += stat.st_size
                    entries.append((stat.st_mtime, stat.st_size, entry.path))
            if total <= max_size:
                return
            target = int(max_size * 0.9)
            entries.sort()  # oldest first
            for _, size, path in entries:
                if total <= target:
                    break
                try:
                    os.unlink(path)
                    total -= size
                except OSError:
                    pass
        except OSError:
            log.warning("Cache eviction failed", exc_info=True)


__all__ = [
    "ART_TYPES",
    "ArtworkCache",
    "ArtworkError",
    "ArtworkResult",
    "MEDIA_TYPES",
    "UnsafeArtworkSource",
]
