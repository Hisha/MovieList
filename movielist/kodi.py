"""Read-only data access for the Kodi MyVideos database (Kodi 21 Omega).

All SQL lives in this module.  Only SELECT statements are issued; the
underlying connections additionally run in READ ONLY transaction mode
(see db.py) and the production account is SELECT-only.

Column mappings were verified against Kodi 21 (Omega) source,
xbmc/video/VideoDatabase.{h,cpp} (MyVideos131):

  movie_view   c00 title, c01 plot, c02 plotoutline, c03 tagline,
               c11 runtime, c12 mpaa, c13 top250, c14 genre display,
               c15 director, c16 originaltitle, c18 studios,
               premiered, dateAdded (from files), rating, votes,
               uniqueid_value, uniqueid_type
  tvshow_view  c00 title, c01 plot, c02 status, c05 premiered,
               c08 genre display, c13 mpaa, c14 studios, c15 sorttitle,
               dateAdded (max episode dateAdded), rating, votes,
               uniqueid_value, uniqueid_type, totalCount, totalSeasons
  season_view  idSeason, idShow, season, name, episodes (cataloged
               episode count), aired (earliest first-aired)
  episode_view c00 title, c01 plot, c05 firstaired, c12 season,
               c13 episode, dateAdded, rating, uniqueid_value,
               uniqueid_type
  art          art_id, media_id, media_type, type, url
  actor        actor_id, name          actor_link: actor_id, media_id,
               media_type
  genre        genre_id, name          genre_link: genre_id, media_id,
               media_type
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from .db import Database, DatabaseUnavailable

log = logging.getLogger(__name__)

# Whitelisted sort clauses (static strings only; never user input).
MOVIE_SORTS: dict[str, str] = {
    "newest": "m.dateAdded DESC, m.idMovie DESC",
    "oldest": "m.dateAdded ASC, m.idMovie ASC",
    "az": "m.c00 ASC, m.idMovie ASC",
    "za": "m.c00 DESC, m.idMovie DESC",
    "year": "CAST(m.premiered AS UNSIGNED) DESC, m.c00 ASC",
    "rating": "m.rating DESC, m.c00 ASC, m.idMovie ASC",
}

SHOW_SORTS: dict[str, str] = {
    "newest": "s.dateAdded DESC, s.idShow DESC",
    "az": "s.c00 ASC, s.idShow ASC",
    "za": "s.c00 DESC, s.idShow DESC",
    "year": "CAST(s.c05 AS UNSIGNED) DESC, s.c00 ASC",
    "rating": "s.rating DESC, s.c00 ASC, s.idShow ASC",
    "episodes": "s.totalCount DESC, s.c00 ASC",
}

_MOVIE_COLUMNS = """
    m.idMovie AS idMovie,
    m.c00 AS title,
    m.c01 AS plot,
    m.c02 AS plotoutline,
    m.c03 AS tagline,
    m.c11 AS runtime,
    m.c12 AS mpaa,
    m.c14 AS genres,
    m.c15 AS directors,
    m.c16 AS originaltitle,
    m.c18 AS studios,
    m.premiered AS premiered,
    m.dateAdded AS dateadded,
    m.rating AS rating,
    m.votes AS votes,
    m.uniqueid_value AS uniqueid_value,
    m.uniqueid_type AS uniqueid_type
"""

_SHOW_COLUMNS = """
    s.idShow AS idShow,
    s.c00 AS title,
    s.c01 AS plot,
    s.c02 AS status,
    s.c05 AS premiered,
    s.c08 AS genres,
    s.c13 AS mpaa,
    s.c14 AS studios,
    s.dateAdded AS dateadded,
    s.rating AS rating,
    s.votes AS votes,
    s.uniqueid_value AS uniqueid_value,
    s.uniqueid_type AS uniqueid_type,
    COALESCE(s.totalCount, 0) AS episode_count,
    COALESCE(s.totalSeasons, 0) AS season_count
"""

_EPISODE_COLUMNS = """
    e.idEpisode AS idEpisode,
    e.c00 AS title,
    e.c01 AS plot,
    e.c05 AS firstaired,
    e.c12 AS seasonnum,
    e.c13 AS episodenum,
    e.dateAdded AS dateadded,
    e.rating AS rating,
    e.uniqueid_value AS uniqueid_value,
    e.uniqueid_type AS uniqueid_type
"""


@dataclass
class Page:
    items: list[dict[str, Any]]
    total: int
    page: int
    page_size: int

    @property
    def pages(self) -> int:
        if self.page_size <= 0 or self.total <= 0:
            return 1
        return max(1, (self.total + self.page_size - 1) // self.page_size)

    @property
    def has_next(self) -> bool:
        return self.page < self.pages


def _year(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(str(value)[:4])
    except (ValueError, TypeError):
        return None


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_movie(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["idMovie"]),
        "title": row.get("title") or "Unknown Title",
        "originaltitle": row.get("originaltitle") or None,
        "plot": row.get("plot") or "",
        "plotoutline": row.get("plotoutline") or "",
        "tagline": row.get("tagline") or "",
        "genres": row.get("genres") or "",
        "directors": row.get("directors") or "",
        "studios": row.get("studios") or "",
        "mpaa": row.get("mpaa") or "",
        "runtime": int(row["runtime"]) if _number(row.get("runtime")) else None,
        "year": _year(row.get("premiered")),
        "premiered": row.get("premiered") or None,
        "dateadded": row.get("dateadded") or None,
        "rating": _number(row.get("rating")),
        "votes": int(row["votes"]) if _number(row.get("votes")) else None,
        "uniqueid": row.get("uniqueid_value") or None,
        "uniqueid_type": row.get("uniqueid_type") or None,
    }


def normalize_show(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["idShow"]),
        "title": row.get("title") or "Unknown Show",
        "plot": row.get("plot") or "",
        "status": row.get("status") or "",
        "genres": row.get("genres") or "",
        "studios": row.get("studios") or "",
        "mpaa": row.get("mpaa") or "",
        "year": _year(row.get("premiered")),
        "premiered": row.get("premiered") or None,
        "dateadded": row.get("dateadded") or None,
        "rating": _number(row.get("rating")),
        "votes": int(row["votes"]) if _number(row.get("votes")) else None,
        "uniqueid": row.get("uniqueid_value") or None,
        "uniqueid_type": row.get("uniqueid_type") or None,
        "episode_count": int(row.get("episode_count") or 0),
        "season_count": int(row.get("season_count") or 0),
    }


def normalize_season(row: dict[str, Any]) -> dict[str, Any]:
    number = int(row["season"])
    return {
        "id": int(row["idSeason"]),
        "number": number,
        "name": row.get("name") or ("Specials" if number == 0 else f"Season {number}"),
        "episode_count": int(row.get("episodes") or 0),
        "aired": row.get("aired") or None,
    }


def normalize_episode(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["idEpisode"]),
        "title": row.get("title") or "Unknown Episode",
        "plot": row.get("plot") or "",
        "firstaired": row.get("firstaired") or None,
        "season": int(row["seasonnum"]) if str(row.get("seasonnum") or "").strip() != "" else None,
        "episode": int(row["episodenum"]) if str(row.get("episodenum") or "").strip() != "" else None,
        "dateadded": row.get("dateadded") or None,
        "rating": _number(row.get("rating")),
        "uniqueid": row.get("uniqueid_value") or None,
        "uniqueid_type": row.get("uniqueid_type") or None,
    }


def _movie_filters(
    search: str | None, genre: str | None
) -> tuple[list[str], list[Any]]:
    where: list[str] = []
    params: list[Any] = []
    if search:
        where.append(
            "(m.c00 LIKE %s"
            " OR EXISTS (SELECT 1 FROM actor_link al"
            "   JOIN actor a ON a.actor_id = al.actor_id"
            "   WHERE al.media_id = m.idMovie AND al.media_type = 'movie'"
            "     AND a.name LIKE %s)"
            " OR EXISTS (SELECT 1 FROM genre_link gl"
            "   JOIN genre g ON g.genre_id = gl.genre_id"
            "   WHERE gl.media_id = m.idMovie AND gl.media_type = 'movie'"
            "     AND g.name LIKE %s))"
        )
        like = f"%{search}%"
        params.extend([like, like, like])
    if genre:
        where.append(
            "EXISTS (SELECT 1 FROM genre_link gl"
            "  JOIN genre g ON g.genre_id = gl.genre_id"
            "  WHERE gl.media_id = m.idMovie AND gl.media_type = 'movie'"
            "    AND g.name = %s)"
        )
        params.append(genre)
    return where, params


def _show_filters(
    search: str | None, genre: str | None
) -> tuple[list[str], list[Any]]:
    where: list[str] = []
    params: list[Any] = []
    if search:
        where.append(
            "(s.c00 LIKE %s"
            " OR EXISTS (SELECT 1 FROM actor_link al"
            "   JOIN actor a ON a.actor_id = al.actor_id"
            "   WHERE al.media_id = s.idShow AND al.media_type = 'tvshow'"
            "     AND a.name LIKE %s)"
            " OR EXISTS (SELECT 1 FROM genre_link gl"
            "   JOIN genre g ON g.genre_id = gl.genre_id"
            "   WHERE gl.media_id = s.idShow AND gl.media_type = 'tvshow'"
            "     AND g.name LIKE %s))"
        )
        like = f"%{search}%"
        params.extend([like, like, like])
    if genre:
        where.append(
            "EXISTS (SELECT 1 FROM genre_link gl"
            "  JOIN genre g ON g.genre_id = gl.genre_id"
            "  WHERE gl.media_id = s.idShow AND gl.media_type = 'tvshow'"
            "    AND g.name = %s)"
        )
        params.append(genre)
    return where, params


class KodiRepository:
    """All approved read operations against the Kodi video library."""

    def __init__(self, db: Database):
        self._db = db

    # -- collection statistics -------------------------------------------

    def stats(self) -> dict[str, int]:
        row = self._db.query_one(
            "SELECT"
            " (SELECT COUNT(*) FROM movie) AS movies,"
            " (SELECT COUNT(*) FROM tvshow) AS shows,"
            " (SELECT COUNT(*) FROM episode) AS episodes"
        )
        row = row or {}
        return {
            "movies": int(row.get("movies") or 0),
            "shows": int(row.get("shows") or 0),
            "episodes": int(row.get("episodes") or 0),
        }

    # -- movies -----------------------------------------------------------

    def list_movies(
        self,
        *,
        search: str | None = None,
        genre: str | None = None,
        sort: str = "newest",
        page: int = 1,
        page_size: int = 48,
    ) -> Page:
        order = MOVIE_SORTS.get(sort, MOVIE_SORTS["newest"])
        where, params = _movie_filters(search, genre)
        where_sql = (" WHERE " + " AND ".join(where)) if where else ""

        total_row = self._db.query_one(
            f"SELECT COUNT(*) AS total FROM movie_view m{where_sql}",  # noqa: S608 - static fragments
            params,
        )
        total = int((total_row or {}).get("total") or 0)

        offset = (max(1, page) - 1) * page_size
        rows = self._db.query(
            f"SELECT {_MOVIE_COLUMNS}"  # noqa: S608
            f" FROM movie_view m{where_sql}"
            f" ORDER BY {order}"
            f" LIMIT %s OFFSET %s",
            [*params, page_size, offset],
        )
        return Page(
            items=[normalize_movie(r) for r in rows],
            total=total,
            page=max(1, page),
            page_size=page_size,
        )

    def get_movie(self, movie_id: int) -> dict[str, Any] | None:
        row = self._db.query_one(
            f"SELECT {_MOVIE_COLUMNS} FROM movie_view m WHERE m.idMovie = %s",  # noqa: S608
            (movie_id,),
        )
        return normalize_movie(row) if row else None

    def recently_added_movies(self, limit: int = 12) -> list[dict[str, Any]]:
        rows = self._db.query(
            f"SELECT {_MOVIE_COLUMNS} FROM movie_view m"  # noqa: S608
            " WHERE m.dateAdded IS NOT NULL"
            " ORDER BY m.dateAdded DESC, m.idMovie DESC LIMIT %s",
            (limit,),
        )
        return [normalize_movie(r) for r in rows]

    def movie_genres(self) -> list[str]:
        rows = self._db.query(
            "SELECT DISTINCT g.name AS name FROM genre g"
            " JOIN genre_link gl ON gl.genre_id = g.genre_id"
            " WHERE gl.media_type = 'movie'"
            " ORDER BY g.name"
        )
        return [r["name"] for r in rows if r.get("name")]

    # -- television ---------------------------------------------------------

    def list_shows(
        self,
        *,
        search: str | None = None,
        genre: str | None = None,
        sort: str = "az",
        page: int = 1,
        page_size: int = 36,
    ) -> Page:
        order = SHOW_SORTS.get(sort, SHOW_SORTS["az"])
        where, params = _show_filters(search, genre)
        where_sql = (" WHERE " + " AND ".join(where)) if where else ""

        total_row = self._db.query_one(
            f"SELECT COUNT(*) AS total FROM tvshow_view s{where_sql}",  # noqa: S608
            params,
        )
        total = int((total_row or {}).get("total") or 0)

        offset = (max(1, page) - 1) * page_size
        rows = self._db.query(
            f"SELECT {_SHOW_COLUMNS}"  # noqa: S608
            f" FROM tvshow_view s{where_sql}"
            f" ORDER BY {order}"
            f" LIMIT %s OFFSET %s",
            [*params, page_size, offset],
        )
        return Page(
            items=[normalize_show(r) for r in rows],
            total=total,
            page=max(1, page),
            page_size=page_size,
        )

    def get_show(self, show_id: int) -> dict[str, Any] | None:
        row = self._db.query_one(
            f"SELECT {_SHOW_COLUMNS} FROM tvshow_view s WHERE s.idShow = %s",  # noqa: S608
            (show_id,),
        )
        return normalize_show(row) if row else None

    def list_seasons(self, show_id: int) -> list[dict[str, Any]]:
        rows = self._db.query(
            "SELECT sv.idSeason AS idSeason, sv.season AS season,"
            " sv.name AS name, sv.episodes AS episodes, sv.aired AS aired"
            " FROM season_view sv"
            " WHERE sv.idShow = %s"
            " ORDER BY sv.season ASC",
            (show_id,),
        )
        return [normalize_season(r) for r in rows]

    def list_episodes(self, show_id: int, season: int) -> list[dict[str, Any]]:
        rows = self._db.query(
            f"SELECT {_EPISODE_COLUMNS}"  # noqa: S608
            " FROM episode_view e"
            " WHERE e.idShow = %s AND e.c12 = %s"
            " ORDER BY CAST(e.c13 AS UNSIGNED) ASC, e.idEpisode ASC",
            (show_id, str(season)),
        )
        return [normalize_episode(r) for r in rows]

    def recently_updated_shows(self, limit: int = 12) -> list[dict[str, Any]]:
        rows = self._db.query(
            f"SELECT {_SHOW_COLUMNS} FROM tvshow_view s"  # noqa: S608
            " WHERE s.dateAdded IS NOT NULL"
            " ORDER BY s.dateAdded DESC, s.idShow DESC LIMIT %s",
            (limit,),
        )
        return [normalize_show(r) for r in rows]

    def show_genres(self) -> list[str]:
        rows = self._db.query(
            "SELECT DISTINCT g.name AS name FROM genre g"
            " JOIN genre_link gl ON gl.genre_id = g.genre_id"
            " WHERE gl.media_type = 'tvshow'"
            " ORDER BY g.name"
        )
        return [r["name"] for r in rows if r.get("name")]

    # -- search --------------------------------------------------------------

    def search(
        self, query: str, *, limit: int = 12
    ) -> dict[str, list[dict[str, Any]]]:
        """Unified search across movie and TV show titles, actors, genres."""
        movies = self.list_movies(search=query, sort="az", page=1, page_size=limit)
        shows = self.list_shows(search=query, sort="az", page=1, page_size=limit)
        return {"movies": movies.items, "shows": shows.items}

    # -- artwork references ----------------------------------------------------

    def artwork_urls(
        self, media_type: str, media_id: int, art_type: str, *, limit: int = 3
    ) -> list[str]:
        """Candidate artwork URLs for a media item, best first.

        Rows whose URL starts with http(s) are preferred because they do
        not depend on local media mounts; ties are broken by art_id.
        """
        rows = self._db.query(
            "SELECT url FROM art"
            " WHERE media_id = %s AND media_type = %s AND type = %s"
            " ORDER BY (url LIKE 'http%%') DESC, art_id ASC"
            " LIMIT %s",
            (media_id, media_type, art_type, limit),
        )
        return [r["url"] for r in rows if r.get("url")]

    def ping(self) -> bool:
        return self._db.ping()

    def close(self) -> None:
        self._db.close()


__all__ = [
    "DatabaseUnavailable",
    "KodiRepository",
    "MOVIE_SORTS",
    "SHOW_SORTS",
    "Page",
]
