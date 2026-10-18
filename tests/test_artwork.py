"""Artwork cache behavior tests (local files, remote fetcher, failures)."""

from __future__ import annotations

from pathlib import Path

import pytest

from movielist.artwork import ArtworkCache, ArtworkError, UnsafeArtworkSource
from tests.conftest import FakeRepo, png_bytes


def cache_for(settings, repo, fetcher=None) -> ArtworkCache:
    return ArtworkCache(settings, repo, fetcher=fetcher or (lambda url: b""))


def test_local_file_via_smb_mapping(settings, repo, media_root):
    target = media_root / "Movies" / "Alpha" / "poster.jpg"
    target.parent.mkdir(parents=True)
    target.write_bytes(png_bytes())
    repo.art_urls[("movie", 1, "poster")] = [
        "smb://nas/MediaDrive/Movies/Alpha/poster.jpg"
    ]
    cache = cache_for(settings, repo)
    result = cache.get("movie", 1, "poster")
    assert result.path.exists()
    assert result.content_type == "image/png"
    assert result.path.parent == Path(settings.artwork_cache_dir)
    # Second call is a cache hit with the same file
    again = cache.get("movie", 1, "poster")
    assert again.path == result.path


def test_absolute_local_path_under_allowed_dir(settings, repo, media_root):
    target = media_root / "TV" / "show-fanart.png"
    target.parent.mkdir(parents=True)
    target.write_bytes(png_bytes(16, 9))
    # absolute path is allowed because it lives under a mapping target
    repo.art_urls[("tvshow", 2, "fanart")] = [str(target)]
    cache = cache_for(settings, repo)
    result = cache.get("tvshow", 2, "fanart")
    assert result.path.exists()
    assert result.content_type == "image/png"


def test_missing_artwork_returns_placeholder(settings, repo):
    cache = cache_for(settings, repo)
    result = cache.get("movie", 42, "poster")
    assert result.path.name == "no-poster.png"


def test_no_artwork_rows_returns_placeholder(settings, repo):
    cache = cache_for(settings, repo)
    assert cache.get("movie", 1, "poster").path.name == "no-poster.png"


def test_failed_remote_download_negative_cached(settings, repo):
    calls = []

    def failing_fetcher(url):
        calls.append(url)
        raise ArtworkError("boom")

    repo.art_urls[("movie", 1, "poster")] = ["https://image.tmdb.org/x.jpg"]
    cache = cache_for(settings, repo, failing_fetcher)
    first = cache.get("movie", 1, "poster")
    second = cache.get("movie", 1, "poster")
    assert first.path.name == "no-poster.png"
    assert second.path.name == "no-poster.png"
    assert len(calls) == 1  # not re-fetched on the second request


def test_candidate_order_tries_next_url(settings, repo):
    def fetcher(url):
        if "good" in url:
            return png_bytes()
        raise ArtworkError("first source broken")

    repo.art_urls[("movie", 1, "poster")] = [
        "https://image.tmdb.org/bad.jpg",
        "https://image.tmdb.org/good.jpg",
    ]
    cache = cache_for(settings, repo, fetcher)
    result = cache.get("movie", 1, "poster")
    assert result.path.name != "no-poster.png"


def test_remote_fetch_caches_bytes(settings, repo):
    repo.art_urls[("movie", 3, "poster")] = ["https://image.tmdb.org/p.jpg"]
    cache = cache_for(settings, repo, lambda url: png_bytes(20, 30))
    result = cache.get("movie", 3, "poster")
    assert result.path.exists()
    assert result.path.stat().st_size > 0
    # The cached file must itself be a valid image
    assert result.content_type == "image/png"


def test_non_image_remote_bytes_rejected(settings, repo):
    repo.art_urls[("movie", 3, "poster")] = ["https://image.tmdb.org/p.jpg"]
    cache = cache_for(settings, repo, lambda url: b"<html>not an image</html>")
    result = cache.get("movie", 3, "poster")
    assert result.path.name == "no-poster.png"


def test_oversized_local_file_rejected(settings, repo, media_root):
    big = media_root / "big.png"
    big.write_bytes(b"\x89PNG" + b"x" * (settings.artwork_max_bytes + 10))
    repo.art_urls[("movie", 1, "poster")] = [str(big)]
    cache = cache_for(settings, repo)
    result = cache.get("movie", 1, "poster")
    assert result.path.name == "no-poster.png"


def test_image_dimensions_limit(settings, repo):
    repo.art_urls[("movie", 1, "poster")] = ["https://image.tmdb.org/p.jpg"]
    # 2500px exceeds settings.artwork_max_dimension (2000)
    cache = cache_for(
        settings, repo, lambda url: png_bytes(2500, 10)
    )
    result = cache.get("movie", 1, "poster")
    assert result.path.name == "no-poster.png"


def test_cache_eviction_respects_max_size(settings, repo, media_root):
    import os

    from PIL import Image

    def noise_png(w=120, h=180):
        import io
        buf = io.BytesIO()
        Image.frombytes("RGB", (w, h), os.urandom(w * h * 3)).save(
            buf, format="PNG"
        )
        return buf.getvalue()

    object.__setattr__(settings, "artwork_cache_max_size", 120_000)
    for i in range(6):
        url = f"https://image.tmdb.org/img{i}.jpg"
        repo.art_urls[("movie", i + 1, "poster")] = [url]
        cache = cache_for(settings, repo, lambda u: noise_png())
        result = cache.get("movie", i + 1, "poster")
        assert result.path.exists()
    cache_dir = Path(settings.artwork_cache_dir)
    total = sum(f.stat().st_size for f in cache_dir.iterdir() if f.is_file())
    assert total <= settings.artwork_cache_max_size


def test_unsupported_request_rejected(settings, repo):
    cache = cache_for(settings, repo)
    with pytest.raises(UnsafeArtworkSource):
        cache.get("album", 1, "poster")
    with pytest.raises(UnsafeArtworkSource):
        cache.get("movie", 0, "poster")
    with pytest.raises(UnsafeArtworkSource):
        cache.get("movie", 1, "wat")
