"""Application configuration loaded from environment / .env file.

All deployment-specific values come from the environment.  Nothing here
is hardcoded with real credentials or site-specific addresses.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent


def _env(key: str, default: str | None = None) -> str | None:
    value = os.getenv(key)
    if value is None or value == "":
        return default
    return value


def _env_int(key: str, default: int) -> int:
    raw = _env(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"{key} must be an integer, got {raw!r}")


def _parse_path_mappings(raw: str | None) -> dict[str, str]:
    """Parse MEDIA_PATH_MAPPINGS.

    Accepted forms (comma separated):

        smb://nas/MediaDrive/=/mnt/MediaDrive,smb://nas/Backup/=/mnt/Backup

    or a JSON object:

        {"smb://nas/MediaDrive/": "/mnt/MediaDrive"}
    """
    if not raw:
        return {}
    raw = raw.strip()
    mappings: dict[str, str] = {}
    if raw.startswith("{"):
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("MEDIA_PATH_MAPPINGS JSON must be an object")
        items = data.items()
    else:
        pairs = []
        for chunk in raw.split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            if "=" not in chunk:
                raise ValueError(
                    "MEDIA_PATH_MAPPINGS entries must look like "
                    "'smb://host/share/=/local/mount'"
                )
            src, dst = chunk.split("=", 1)
            pairs.append((src.strip(), dst.strip()))
        items = pairs
    for src, dst in items:
        if not src or not dst:
            raise ValueError("MEDIA_PATH_MAPPINGS contains an empty mapping")
        mappings[src] = dst
    return mappings


def _parse_hosts(raw: str | None) -> frozenset[str]:
    if not raw:
        return frozenset()
    return frozenset(h.strip().lower() for h in raw.split(",") if h.strip())


def _parse_dirs(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(p.strip() for p in raw.split(os.pathsep) if p.strip()) or tuple(
        p.strip() for p in raw.split(",") if p.strip()
    )


@dataclass(frozen=True)
class Settings:
    # Kodi database
    kodi_db_host: str = "127.0.0.1"
    kodi_db_port: int = 3306
    kodi_db_name: str = "MyVideos131"
    kodi_db_user: str = "movielist"
    kodi_db_password: str = field(default="", repr=False)
    kodi_db_connect_timeout: int = 5
    kodi_db_read_timeout: int = 15
    kodi_db_pool_size: int = 5

    # Application server
    movielist_host: str = "127.0.0.1"
    movielist_port: int = 8000
    root_path: str = "/ML"

    # UI
    page_size: int = 48
    shows_page_size: int = 36
    recent_count: int = 12

    # Artwork cache
    artwork_cache_dir: str = str(BASE_DIR / "artwork_cache")
    artwork_cache_max_size: int = 2 * 1024 * 1024 * 1024  # 2 GiB
    artwork_connect_timeout: float = 5.0
    artwork_read_timeout: float = 15.0
    artwork_max_bytes: int = 25 * 1024 * 1024
    artwork_max_dimension: int = 10000
    artwork_failure_ttl: int = 3600
    media_path_mappings: dict[str, str] = field(default_factory=dict)
    approved_artwork_hosts: frozenset[str] = frozenset()
    artwork_allowed_dirs: tuple[str, ...] = ()

    # Logging
    log_level: str = "INFO"

    @classmethod
    def load(cls) -> "Settings":
        load_dotenv(BASE_DIR / ".env")

        name = _env("KODI_DB_NAME", "MyVideos131") or "MyVideos131"
        if not name.replace("_", "").isalnum():
            raise ValueError(
                "KODI_DB_NAME may only contain letters, digits and underscores "
                "(it is interpolated into SQL identifiers after verification)"
            )

        root_path = _env("MOVIELIST_ROOT_PATH", "/ML") or "/ML"
        if not root_path.startswith("/"):
            raise ValueError("MOVIELIST_ROOT_PATH must start with '/'")
        root_path = root_path.rstrip("/")

        return cls(
            kodi_db_host=_env("KODI_DB_HOST", "127.0.0.1") or "127.0.0.1",
            kodi_db_port=_env_int("KODI_DB_PORT", 3306),
            kodi_db_name=name,
            kodi_db_user=_env("KODI_DB_USER", "movielist") or "movielist",
            kodi_db_password=_env("KODI_DB_PASSWORD", "") or "",
            kodi_db_connect_timeout=_env_int("KODI_DB_CONNECT_TIMEOUT", 5),
            kodi_db_read_timeout=_env_int("KODI_DB_READ_TIMEOUT", 15),
            kodi_db_pool_size=max(1, _env_int("KODI_DB_POOL_SIZE", 5)),
            movielist_host=_env("MOVIELIST_HOST", "127.0.0.1") or "127.0.0.1",
            movielist_port=_env_int("MOVIELIST_PORT", 8000),
            root_path=root_path,
            page_size=max(1, _env_int("MOVIELIST_PAGE_SIZE", 48)),
            shows_page_size=max(1, _env_int("MOVIELIST_SHOWS_PAGE_SIZE", 36)),
            recent_count=max(1, _env_int("MOVIELIST_RECENT_COUNT", 12)),
            artwork_cache_dir=_env(
                "ARTWORK_CACHE_DIR", str(BASE_DIR / "artwork_cache")
            )
            or str(BASE_DIR / "artwork_cache"),
            artwork_cache_max_size=max(
                10 * 1024 * 1024, _env_int("ARTWORK_CACHE_MAX_SIZE", 2 * 1024**3)
            ),
            artwork_connect_timeout=float(
                _env("ARTWORK_CONNECT_TIMEOUT", "5") or "5"
            ),
            artwork_read_timeout=float(_env("ARTWORK_READ_TIMEOUT", "15") or "15"),
            artwork_max_bytes=max(
                1024, _env_int("ARTWORK_MAX_BYTES", 25 * 1024 * 1024)
            ),
            artwork_max_dimension=max(
                100, _env_int("ARTWORK_MAX_DIMENSION", 10000)
            ),
            artwork_failure_ttl=_env_int("ARTWORK_FAILURE_TTL", 3600),
            media_path_mappings=_parse_path_mappings(_env("MEDIA_PATH_MAPPINGS")),
            approved_artwork_hosts=_parse_hosts(_env("APPROVED_ARTWORK_HOSTS")),
            artwork_allowed_dirs=_parse_dirs(_env("ARTWORK_ALLOWED_DIRS")),
            log_level=(_env("LOG_LEVEL", "INFO") or "INFO").upper(),
        )
