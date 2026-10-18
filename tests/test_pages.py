"""Page rendering tests for the Kodi-backed UI."""

from __future__ import annotations

from tests.conftest import FakeRepo, make_movie, make_show


def test_home_page(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Recently Added Movies" in resp.text
    assert "Recently Updated TV Shows" in resp.text
    assert "Movies" in resp.text and "TV Shows" in resp.text


def test_home_page_stats(client, repo):
    repo.movies.append(make_movie(99))
    resp = client.get("/")
    assert resp.status_code == 200
    assert ">6<" in resp.text.replace(" ", "")  # 6 movies after append


def test_movies_page_renders_grid(client):
    resp = client.get("/movies")
    assert resp.status_code == 200
    assert "media-grid" in resp.text
    # default sort is "newest": most recently added movies appear first
    assert "Epsilon" in resp.text


def test_movies_page_search_and_genre(client):
    resp = client.get("/movies", params={"q": "alpha", "genre": "Action"})
    assert resp.status_code == 200
    assert "Alpha" in resp.text
    assert "Epsilon" not in resp.text


def test_movies_page_invalid_sort_falls_back(client):
    resp = client.get("/movies", params={"sort": "'; DROP TABLE movie;--"})
    assert resp.status_code == 200


def test_movie_detail(client):
    resp = client.get("/movies/1")
    assert resp.status_code == 200
    assert "Alpha" in resp.text
    assert "Director One" in resp.text


def test_movie_detail_missing_metadata(client, repo):
    repo.movies.append(make_movie(6, title="Minimal", plot="", tagline=None,
                                   genres=None, directors=None, rating=None,
                                   votes=None, year=None, premiered=None,
                                   mpaa=None, runtime=None, uniqueid=None,
                                   uniqueid_type=None, studios=None))
    resp = client.get("/movies/6")
    assert resp.status_code == 200
    assert "Minimal" in resp.text
    assert "No plot description available." in resp.text


def test_movie_detail_not_found(client):
    resp = client.get("/movies/9999")
    assert resp.status_code == 404
    assert "Not Found" in resp.text


def test_shows_page(client):
    resp = client.get("/shows")
    assert resp.status_code == 200
    assert "Omega Show" in resp.text
    assert "Zeta Show" in resp.text


def test_show_detail_lists_seasons_and_specials(client):
    resp = client.get("/shows/1")
    assert resp.status_code == 200
    assert "Specials" in resp.text          # season 0 label
    assert "Season 1" in resp.text
    # default active season is the first REGULAR season with episodes
    assert "Pilot" in resp.text


def test_show_detail_explicit_specials_season(client):
    resp = client.get("/shows/1", params={"season": 0})
    assert resp.status_code == 200
    assert "Behind the Scenes" in resp.text


def test_show_detail_custom_season_name(client):
    resp = client.get("/shows/2")
    assert resp.status_code == 200
    assert "Book One" in resp.text


def test_show_detail_not_found(client):
    resp = client.get("/shows/42")
    assert resp.status_code == 404


def test_show_without_seasons(client, repo):
    repo.seasons[7] = []
    repo.shows.append(make_show(7, title="Empty Show"))
    resp = client.get("/shows/7")
    assert resp.status_code == 200
    assert "No seasons are cataloged" in resp.text


def test_search_page(client):
    resp = client.get("/search", params={"q": "omega"})
    assert resp.status_code == 200
    assert "Omega Show" in resp.text


def test_search_page_empty_query(client):
    resp = client.get("/search")
    assert resp.status_code == 200


def test_search_no_results(client):
    resp = client.get("/search", params={"q": "zzzznotfound"})
    assert resp.status_code == 200
    assert "Nothing matched" in resp.text


def test_error_page_404(client):
    resp = client.get("/definitely-not-a-page")
    assert resp.status_code == 404
    assert "Not Found" in resp.text


def test_healthz_ok(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
