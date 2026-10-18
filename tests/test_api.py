"""JSON API tests: pagination, search, sorting."""

from __future__ import annotations


def test_movies_api_pagination(client):
    # 5 movies, page size 2
    r1 = client.get("/api/movies", params={"sort": "az", "page": 1}).json()
    assert r1["total"] == 5
    assert r1["pages"] == 3
    assert r1["has_next"] is True
    assert len(r1["items"]) == 2
    assert [i["title"] for i in r1["items"]] == ["Alpha", "Beta"]

    r3 = client.get("/api/movies", params={"sort": "az", "page": 3}).json()
    assert len(r3["items"]) == 1
    assert r3["has_next"] is False


def test_movies_api_search(client):
    data = client.get("/api/movies", params={"q": "alp"}).json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Alpha"


def test_movies_api_genre_filter(client):
    data = client.get("/api/movies", params={"genre": "Drama"}).json()
    titles = {i["title"] for i in data["items"]}
    assert "Beta" in titles and "gamma" in titles
    assert "Alpha" not in titles


def test_movies_api_rating_sort_nulls_last(client):
    ratings = []
    page = 1
    while True:
        data = client.get("/api/movies",
                          params={"sort": "rating", "page": page}).json()
        ratings.extend(i["rating"] for i in data["items"])
        if not data["has_next"]:
            break
        page += 1
    known = [r for r in ratings if r is not None]
    assert known == sorted(known, reverse=True)
    assert ratings[-1] is None  # Delta has no rating


def test_movies_api_item_shape(client):
    item = client.get("/api/movies", params={"sort": "az"}).json()["items"][0]
    assert item["url"].endswith("/movies/1")
    assert item["poster"].endswith("/art/movie/1/poster")
    assert item["year"] == 2001


def test_shows_api(client):
    data = client.get("/api/shows", params={"sort": "az"}).json()
    assert data["total"] == 2
    assert data["items"][0]["title"] == "Omega Show"
    assert "season_count" in data["items"][0]
    assert "episode_count" in data["items"][0]


def test_shows_api_search_actor_genre(client):
    data = client.get("/api/shows", params={"q": "comedy"}).json()
    assert [i["title"] for i in data["items"]] == ["Zeta Show"]


def test_season_episodes_api(client):
    data = client.get("/api/shows/1/seasons/1").json()
    assert data["show_id"] == 1
    assert data["season"] == 1
    titles = [e["title"] for e in data["episodes"]]
    assert titles == ["Pilot", "Second First"]  # sorted by episode number


def test_season_episodes_api_empty_season(client):
    data = client.get("/api/shows/1/seasons/9").json()
    assert data["episodes"] == []


def test_season_episodes_api_unknown_show(client):
    resp = client.get("/api/shows/999/seasons/1")
    assert resp.status_code == 404


def test_page_clamped(client):
    data = client.get("/api/movies", params={"page": -5}).json()
    assert data["page"] == 1
    # non-numeric page values are rejected by validation
    assert client.get("/api/movies", params={"page": "abc"}).status_code == 422
