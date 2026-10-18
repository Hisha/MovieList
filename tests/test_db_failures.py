"""Database outage handling: pages and APIs fail safely and gracefully."""

from __future__ import annotations

from fastapi.testclient import TestClient

from movielist.app import create_app
from movielist.artwork import ArtworkCache
from movielist.db import DatabaseUnavailable

from tests.conftest import FakeRepo


class BrokenRepo(FakeRepo):
    def __init__(self):
        super().__init__()
        self.fail = True


def make_client(settings):
    repo = BrokenRepo()
    artwork = ArtworkCache(settings, repo, fetcher=lambda url: b"")
    app = create_app(settings=settings, repo=repo, artwork=artwork)
    return TestClient(app, raise_server_exceptions=False), repo


def test_home_page_503_on_outage(settings):
    client, _ = make_client(settings)
    resp = client.get("/")
    assert resp.status_code == 503
    assert "unreachable" in resp.text.lower()


def test_movies_page_503_on_outage(settings):
    client, _ = make_client(settings)
    assert client.get("/movies").status_code == 503


def test_api_503_json_on_outage(settings):
    client, _ = make_client(settings)
    resp = client.get("/api/movies")
    assert resp.status_code == 503
    assert resp.json()["status"] == "error"


def test_healthz_reports_degraded(settings):
    client, _ = make_client(settings)
    resp = client.get("/healthz")
    assert resp.status_code == 503
    assert resp.json() == {"status": "degraded"}


def test_recovery_after_outage(settings):
    client, repo = make_client(settings)
    assert client.get("/").status_code == 503
    repo.fail = False
    assert client.get("/").status_code == 200


def test_no_credentials_in_error_page(settings):
    client, _ = make_client(settings)
    resp = client.get("/")
    assert "secret" not in resp.text
    assert "password" not in resp.text.lower()
    assert "db.example.test" not in resp.text
