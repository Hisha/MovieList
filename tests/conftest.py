"""Shared test fixtures: an in-memory fake Kodi repository and app client."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from movielist.app import create_app
from movielist.artwork import ArtworkCache
from movielist.config import Settings
from movielist.db import DatabaseUnavailable
from movielist.kodi import Page


def make_movie(movie_id: int, **overrides):
    movie = {
        "id": movie_id,
        "title": f"Movie {movie_id}",
        "originaltitle": None,
        "plot": f"Plot for movie {movie_id}.",
        "plotoutline": "",
        "tagline": "",
        "genres": "Action / Comedy",
        "directors": "Director One",
        "studios": "Studio One",
        "mpaa": "PG-13",
        "runtime": 100 + movie_id,
        "year": 2000 + movie_id,
        "premiered": f"{2000 + movie_id}-06-01",
        "dateadded": f"2024-01-{movie_id:02d} 12:00:00",
        "rating": 5.0 + (movie_id % 5),
        "votes": 100 + movie_id,
        "uniqueid": str(1000 + movie_id),
        "uniqueid_type": "tmdb",
    }
    movie.update(overrides)
    return movie


def make_show(show_id: int, **overrides):
    show = {
        "id": show_id,
        "title": f"Show {show_id}",
        "plot": f"Plot for show {show_id}.",
        "status": "Continuing",
        "genres": "Drama",
        "studios": "Network",
        "mpaa": "",
        "year": 2010 + show_id,
        "premiered": f"{2010 + show_id}-01-01",
        "dateadded": f"2024-02-{show_id:02d} 08:00:00",
        "rating": 7.0 + (show_id % 3) / 10,
        "votes": 50 + show_id,
        "uniqueid": str(2000 + show_id),
        "uniqueid_type": "tvdb",
        "episode_count": 10,
        "season_count": 2,
    }
    show.update(overrides)
    return show


def make_episode(episode_id: int, season: int, number: int, **overrides):
    ep = {
        "id": episode_id,
        "title": f"Episode {season}x{number}",
        "plot": "Episode plot.",
        "firstaired": "2015-04-04",
        "season": season,
        "episode": number,
        "dateadded": "2024-01-15 09:00:00",
        "rating": 6.5,
        "uniqueid": None,
        "uniqueid_type": None,
    }
    ep.update(overrides)
    return ep


class FakeRepo:
    """In-memory stand-in for KodiRepository with real filtering."""

    def __init__(self):
        self.movies = [
            make_movie(1, title="Alpha", genres="Action"),
            make_movie(2, title="Beta", genres="Drama", rating=9.1, year=1999,
                       premiered="1999-03-03"),
            make_movie(3, title="gamma", genres="Action / Drama"),
            make_movie(4, title="Delta", genres="Comedy", rating=None,
                       votes=None, plot="", tagline=None, mpaa=None,
                       runtime=None, year=None, premiered=None,
                       uniqueid=None, uniqueid_type=None),
            make_movie(5, title="Epsilon", genres="Sci-Fi"),
        ]
        self.shows = [
            make_show(1, title="Omega Show", genres="Drama / Sci-Fi"),
            make_show(2, title="Zeta Show", genres="Comedy", episode_count=3,
                      season_count=2),
        ]
        self.seasons = {
            1: [
                {"idSeason": 101, "season": 0, "name": None, "episodes": 1,
                 "aired": "2010-06-06"},
                {"idSeason": 102, "season": 1, "name": None, "episodes": 2,
                 "aired": "2010-09-09"},
            ],
            2: [
                {"idSeason": 201, "season": 1, "name": "Book One", "episodes": 3,
                 "aired": "2012-01-01"},
            ],
        }
        self.episodes = {
            (1, 0): [make_episode(1001, 0, 1, title="Behind the Scenes")],
            (1, 1): [
                make_episode(1002, 1, 2, title="Second First"),
                make_episode(1003, 1, 1, title="Pilot"),
            ],
            (2, 1): [
                make_episode(2001, 1, 1),
                make_episode(2002, 1, 2),
                make_episode(2003, 1, 3),
            ],
        }
        self.art_urls: dict[tuple[str, int, str], list[str]] = {}
        self.fail = False

    def _maybe_fail(self):
        if self.fail:
            raise DatabaseUnavailable("simulated outage")

    def stats(self):
        self._maybe_fail()
        return {"movies": len(self.movies), "shows": len(self.shows),
                "episodes": sum(len(v) for v in self.episodes.values())}

    def _paginate(self, items, page, page_size):
        page = max(1, page)
        start = (page - 1) * page_size
        return Page(items[start:start + page_size], len(items), page, page_size)

    def list_movies(self, *, search=None, genre=None, sort="newest",
                    page=1, page_size=48):
        self._maybe_fail()
        items = list(self.movies)
        if search:
            needle = search.lower()
            items = [m for m in items if needle in m["title"].lower()
                     or needle in (m["genres"] or "").lower()]
        if genre:
            items = [m for m in items
                     if genre in [g.strip() for g in (m["genres"] or "").split("/")]]
        key = {
            "newest": lambda m: m["dateadded"] or "",
            "oldest": lambda m: m["dateadded"] or "",
            "az": lambda m: (m["title"] or "").lower(),
            "za": lambda m: (m["title"] or "").lower(),
            "year": lambda m: m["year"] or 0,
            "rating": lambda m: m["rating"] or 0,
        }.get(sort, lambda m: m["dateadded"] or "")
        items.sort(key=key, reverse=sort in ("newest", "za", "year", "rating"))
        return self._paginate(items, page, page_size)

    def get_movie(self, movie_id):
        self._maybe_fail()
        return next((m for m in self.movies if m["id"] == movie_id), None)

    def movie_genres(self):
        self._maybe_fail()
        names = set()
        for m in self.movies:
            for g in (m["genres"] or "").split("/"):
                if g.strip():
                    names.add(g.strip())
        return sorted(names)

    def recently_added_movies(self, limit=12):
        self._maybe_fail()
        items = sorted(self.movies, key=lambda m: m["dateadded"] or "",
                       reverse=True)
        return items[:limit]

    def _filter_shows(self, search, genre):
        items = list(self.shows)
        if search:
            needle = search.lower()
            items = [s for s in items if needle in s["title"].lower()
                     or needle in (s["genres"] or "").lower()]
        if genre:
            items = [s for s in items
                     if genre in [g.strip() for g in (s["genres"] or "").split("/")]]
        return items

    def list_shows(self, *, search=None, genre=None, sort="az", page=1,
                   page_size=36):
        self._maybe_fail()
        items = self._filter_shows(search, genre)
        key = {
            "az": lambda s: s["title"].lower(),
            "za": lambda s: s["title"].lower(),
            "newest": lambda s: s["dateadded"] or "",
            "year": lambda s: s["year"] or 0,
            "rating": lambda s: s["rating"] or 0,
            "episodes": lambda s: s["episode_count"],
        }.get(sort, lambda s: s["title"].lower())
        items.sort(key=key, reverse=sort in ("za", "newest", "year", "rating",
                                             "episodes"))
        return self._paginate(items, page, page_size)

    def get_show(self, show_id):
        self._maybe_fail()
        return next((s for s in self.shows if s["id"] == show_id), None)

    def list_seasons(self, show_id):
        self._maybe_fail()
        from movielist.kodi import normalize_season
        return [normalize_season(s)
                for s in self.seasons.get(show_id, [])]

    def list_episodes(self, show_id, season):
        self._maybe_fail()
        eps = list(self.episodes.get((show_id, season), []))
        eps.sort(key=lambda e: (e["episode"] or 0, e["id"]))
        return eps

    def recently_updated_shows(self, limit=12):
        self._maybe_fail()
        items = sorted(self.shows, key=lambda s: s["dateadded"] or "",
                       reverse=True)
        return items[:limit]

    def show_genres(self):
        self._maybe_fail()
        names = set()
        for s in self.shows:
            for g in (s["genres"] or "").split("/"):
                if g.strip():
                    names.add(g.strip())
        return sorted(names)

    def search(self, query, *, limit=12):
        self._maybe_fail()
        return {
            "movies": self.list_movies(search=query, sort="az", page=1,
                                       page_size=limit).items,
            "shows": self.list_shows(search=query, sort="az", page=1,
                                     page_size=limit).items,
        }

    def artwork_urls(self, media_type, media_id, art_type, *, limit=3):
        self._maybe_fail()
        return list(self.art_urls.get((media_type, media_id, art_type), []))[:limit]

    def ping(self):
        return not self.fail

    def close(self):
        pass


@pytest.fixture
def settings(tmp_path) -> Settings:
    media_root = tmp_path / "media"
    media_root.mkdir()
    return Settings(
        kodi_db_host="db.example.test",
        kodi_db_name="MyVideos131",
        kodi_db_user="movielist",
        kodi_db_password="secret",
        root_path="/ML",
        page_size=2,          # small pages exercise pagination
        shows_page_size=2,
        recent_count=3,
        artwork_cache_dir=str(tmp_path / "cache"),
        artwork_cache_max_size=10 * 1024 * 1024,
        artwork_max_bytes=100_000,
        artwork_max_dimension=2000,
        artwork_failure_ttl=3600,
        media_path_mappings={"smb://nas/MediaDrive/": str(media_root)},
        approved_artwork_hosts=frozenset({"image.tmdb.org"}),
        artwork_allowed_dirs=(),
    )


@pytest.fixture
def media_root(settings) -> Path:
    return Path(settings.media_path_mappings["smb://nas/MediaDrive/"])


@pytest.fixture
def repo() -> FakeRepo:
    return FakeRepo()


def png_bytes(width: int = 8, height: int = 8, color="blue") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def make_app(settings, repo):
    def _make(r: FakeRepo | None = None, artwork: ArtworkCache | None = None,
              fetcher=None) -> TestClient:
        r = r or repo
        if artwork is None:
            artwork = ArtworkCache(settings, r, fetcher=fetcher or (
                lambda url: (_ for _ in ()).throw(RuntimeError("no fetcher"))))
        app = create_app(settings=settings, repo=r, artwork=artwork)
        return TestClient(app, raise_server_exceptions=False)

    return _make


@pytest.fixture
def client(make_app):
    return make_app()
