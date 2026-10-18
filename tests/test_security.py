"""Security tests: artwork path traversal, SSRF, allowlists, unsafe URLs."""

from __future__ import annotations

import httpx
import pytest

from movielist.artwork import (
    ArtworkCache,
    ArtworkError,
    UnsafeArtworkSource,
    _check_remote_address,
    _check_remote_url,
    _fetch_remote,
)
from tests.conftest import png_bytes


def cache_for(settings, repo, fetcher=None) -> ArtworkCache:
    return ArtworkCache(settings, repo, fetcher=fetcher or (lambda url: b""))


# -- local path security ----------------------------------------------------


def test_path_traversal_via_smb_mapping(settings, repo, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("password=hunter2")
    repo.art_urls[("movie", 1, "poster")] = [
        "smb://nas/MediaDrive/../../../secret.txt"
    ]
    cache = cache_for(settings, repo)
    result = cache.get("movie", 1, "poster")
    assert result.path.name == "no-poster.png"  # placeholder, not the secret


def test_absolute_path_outside_allowed_dirs(settings, repo):
    repo.art_urls[("movie", 1, "poster")] = ["/etc/passwd"]
    cache = cache_for(settings, repo)
    result = cache.get("movie", 1, "poster")
    assert result.path.name == "no-poster.png"


def test_disallowed_file_extension(settings, repo, media_root):
    evil = media_root / "notes.txt"
    evil.write_text("not an image")
    repo.art_urls[("movie", 1, "poster")] = [str(evil)]
    cache = cache_for(settings, repo)
    assert cache.get("movie", 1, "poster").path.name == "no-poster.png"


def test_unmapped_smb_path_rejected(settings, repo):
    repo.art_urls[("movie", 1, "poster")] = [
        "smb://otherhost/Share/poster.jpg"
    ]
    cache = cache_for(settings, repo)
    assert cache.get("movie", 1, "poster").path.name == "no-poster.png"


def test_file_scheme_rejected(settings, repo):
    repo.art_urls[("movie", 1, "poster")] = ["file:///etc/passwd"]
    cache = cache_for(settings, repo)
    assert cache.get("movie", 1, "poster").path.name == "no-poster.png"


def test_ftp_scheme_rejected(settings, repo):
    repo.art_urls[("movie", 1, "poster")] = ["ftp://image.tmdb.org/x.jpg"]
    cache = cache_for(settings, repo)
    assert cache.get("movie", 1, "poster").path.name == "no-poster.png"


# -- remote URL security ------------------------------------------------------


def test_remote_scheme_checks():
    from urllib.parse import urlsplit

    with pytest.raises(UnsafeArtworkSource):
        _check_remote_url(urlsplit("http://169.254.169.254/latest/meta"),
                          frozenset({"image.tmdb.org"}))
    with pytest.raises(UnsafeArtworkSource):
        _check_remote_url(urlsplit("ftp://image.tmdb.org/x"),
                          frozenset({"image.tmdb.org"}))
    # not on the allowlist
    with pytest.raises(UnsafeArtworkSource):
        _check_remote_url(urlsplit("https://evil.example.com/x"),
                          frozenset({"image.tmdb.org"}))
    # allowlisted host is fine (no DNS here)
    _check_remote_url(urlsplit("https://image.tmdb.org/x"),
                      frozenset({"image.tmdb.org"}))


def test_remote_address_private_rejected(monkeypatch):
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda host, port, *a, **k: [(2, 1, 6, "", ("10.0.0.5", port or 443))],
    )
    with pytest.raises(UnsafeArtworkSource):
        _check_remote_address("image.tmdb.org", 443)


def test_remote_address_loopback_rejected(monkeypatch):
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda host, port, *a, **k: [(2, 1, 6, "", ("127.0.0.1", port or 443))],
    )
    with pytest.raises(UnsafeArtworkSource):
        _check_remote_address("image.tmdb.org", 443)


def test_remote_address_public_ok(monkeypatch):
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda host, port, *a, **k: [(2, 1, 6, "", ("8.8.8.8", port or 443))],
    )
    _check_remote_address("image.tmdb.org", 443)


# -- fetch-level tests with httpx.MockTransport ---------------------------------


def mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler),
                        follow_redirects=False)


def fetch_settings(settings):
    return settings


def test_fetch_remote_success(settings, monkeypatch):
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda host, port, *a, **k: [(2, 1, 6, "", ("8.8.8.8", port or 443))],
    )
    body = png_bytes()

    def handler(request):
        return httpx.Response(200, headers={"content-type": "image/png"},
                              content=body)

    with mock_client(handler) as client:
        data = _fetch_remote("https://image.tmdb.org/p.jpg", settings, client)
    assert data == body


def test_fetch_remote_redirect_to_private_ip_blocked(settings, monkeypatch):
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda host, port, *a, **k: [(2, 1, 6, "", ("8.8.8.8", port or 443))],
    )

    def handler(request):
        return httpx.Response(
            302, headers={"location": "http://169.254.169.254/steal"}
        )

    with mock_client(handler) as client:
        with pytest.raises(UnsafeArtworkSource):
            _fetch_remote("https://image.tmdb.org/p.jpg", settings, client)


def test_fetch_remote_redirect_to_disallowed_host_blocked(settings, monkeypatch):
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda host, port, *a, **k: [(2, 1, 6, "", ("8.8.8.8", port or 443))],
    )

    def handler(request):
        return httpx.Response(302, headers={
            "location": "https://evil.example.com/p.jpg"})

    with mock_client(handler) as client:
        with pytest.raises(UnsafeArtworkSource):
            _fetch_remote("https://image.tmdb.org/p.jpg", settings, client)


def test_fetch_remote_too_many_redirects(settings, monkeypatch):
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda host, port, *a, **k: [(2, 1, 6, "", ("8.8.8.8", port or 443))],
    )

    def handler(request):
        return httpx.Response(302, headers={
            "location": "https://image.tmdb.org/loop.jpg"})

    with mock_client(handler) as client:
        with pytest.raises(ArtworkError):
            _fetch_remote("https://image.tmdb.org/p.jpg", settings, client)


def test_fetch_remote_non_image_content_type(settings, monkeypatch):
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda host, port, *a, **k: [(2, 1, 6, "", ("8.8.8.8", port or 443))],
    )

    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/html"},
                              content=b"<html></html>")

    with mock_client(handler) as client:
        with pytest.raises(ArtworkError):
            _fetch_remote("https://image.tmdb.org/p.jpg", settings, client)


def test_fetch_remote_oversized_content_length(settings, monkeypatch):
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda host, port, *a, **k: [(2, 1, 6, "", ("8.8.8.8", port or 443))],
    )

    def handler(request):
        return httpx.Response(200, headers={
            "content-type": "image/png",
            "content-length": str(settings.artwork_max_bytes + 1)},
            content=png_bytes())

    with mock_client(handler) as client:
        with pytest.raises(ArtworkError):
            _fetch_remote("https://image.tmdb.org/p.jpg", settings, client)


def test_fetch_remote_http_error(settings, monkeypatch):
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda host, port, *a, **k: [(2, 1, 6, "", ("8.8.8.8", port or 443))],
    )

    def handler(request):
        return httpx.Response(404)

    with mock_client(handler) as client:
        with pytest.raises(ArtworkError):
            _fetch_remote("https://image.tmdb.org/p.jpg", settings, client)


# -- endpoint-level security ------------------------------------------------------


def test_art_endpoint_rejects_bad_types(client):
    assert client.get("/art/bogus/1/poster").status_code == 404
    assert client.get("/art/movie/1/bogus").status_code == 404


def test_art_endpoint_rejects_nonpositive_id(client):
    assert client.get("/art/movie/0/poster").status_code == 400
    assert client.get("/art/movie/-3/poster").status_code == 400


def test_art_endpoint_traversal_shape_404(client):
    assert client.get("/art/movie/../poster").status_code in (404, 400)
    assert client.get("/art/movie/1/poster/../../x").status_code in (404, 400)


def test_no_kodi_urls_leaked_to_html(client, repo):
    repo.art_urls[("movie", 1, "poster")] = [
        "https://image.tmdb.org/secret-poster.jpg"
    ]
    html = client.get("/movies/1").text
    assert "secret-poster.jpg" not in html
    assert "image.tmdb.org" not in html
