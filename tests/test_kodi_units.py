"""Unit tests for the Kodi data layer helpers (no database needed)."""

from __future__ import annotations

from movielist.kodi import (
    MOVIE_SORTS,
    SHOW_SORTS,
    Page,
    _movie_filters,
    _show_filters,
    normalize_episode,
    normalize_movie,
    normalize_season,
    normalize_show,
)


def test_sort_whitelists_are_static_clauses():
    for clause in list(MOVIE_SORTS.values()) + list(SHOW_SORTS.values()):
        assert "%" not in clause
        assert ";" not in clause
        assert "\n" not in clause
        assert clause.strip().upper().startswith(
            ("M.", "S.", "CAST(")
        )


def test_movie_filters_bind_parameters():
    where, params = _movie_filters("O'Brien", "Sci-Fi")
    assert len(where) == 2
    assert params == ["%O'Brien%"] * 3 + ["Sci-Fi"]
    assert "%s" in where[0]
    assert all(p not in where[0] for p in params)  # never interpolated


def test_movie_filters_empty():
    where, params = _movie_filters(None, None)
    assert where == [] and params == []


def test_show_filters_bind_parameters():
    where, params = _show_filters("x", None)
    assert params == ["%x%"] * 3


def test_page_math():
    page = Page(items=[], total=0, page=1, page_size=48)
    assert page.pages == 1 and page.has_next is False
    page = Page(items=[], total=49, page=1, page_size=48)
    assert page.pages == 2 and page.has_next is True
    page = Page(items=[], total=49, page=2, page_size=48)
    assert page.has_next is False


def test_normalize_movie_missing_fields():
    movie = normalize_movie({"idMovie": 7})
    assert movie["id"] == 7
    assert movie["title"] == "Unknown Title"
    assert movie["plot"] == ""
    assert movie["rating"] is None
    assert movie["year"] is None
    assert movie["runtime"] is None
    assert movie["votes"] is None


def test_normalize_movie_values():
    movie = normalize_movie({
        "idMovie": 3, "title": "T", "premiered": "2001-05-04",
        "rating": "7.60", "votes": "123", "runtime": "114",
    })
    assert movie["year"] == 2001
    assert movie["rating"] == 7.6
    assert movie["votes"] == 123
    assert movie["runtime"] == 114


def test_normalize_show_missing_fields():
    show = normalize_show({"idShow": 9})
    assert show["id"] == 9
    assert show["episode_count"] == 0
    assert show["season_count"] == 0
    assert show["rating"] is None


def test_normalize_season_specials():
    season = normalize_season({"idSeason": 1, "season": 0})
    assert season["name"] == "Specials"
    assert season["number"] == 0
    season = normalize_season({"idSeason": 2, "season": 3})
    assert season["name"] == "Season 3"
    season = normalize_season({"idSeason": 3, "season": 1, "name": "Book One"})
    assert season["name"] == "Book One"


def test_normalize_episode_missing_and_multi():
    ep = normalize_episode({
        "idEpisode": 5, "seasonnum": "2", "episodenum": "11",
    })
    assert ep["season"] == 2
    assert ep["episode"] == 11
    assert ep["title"] == "Unknown Episode"
    # Multi-episode files: Kodi stores separate episode rows; each
    # normalizes independently with its own number.
    ep2 = normalize_episode({
        "idEpisode": 6, "seasonnum": "2", "episodenum": "12",
    })
    assert ep2["episode"] == 12
    # Empty/missing numbers stay None instead of crashing.
    ep3 = normalize_episode({"idEpisode": 7, "seasonnum": "", "episodenum": None})
    assert ep3["season"] is None and ep3["episode"] is None
