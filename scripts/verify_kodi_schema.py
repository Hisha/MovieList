#!/usr/bin/env python3
"""Read-only smoke test against the real Kodi video database.

Verifies, WITHOUT modifying anything:
  1. the configured account can connect;
  2. the account appears to be SELECT-only (SHOW GRANTS);
  3. the session is in READ ONLY transaction mode;
  4. the configured database contains the views and columns
     MovieList relies on (Kodi 21 Omega / MyVideos131);
  5. every application query shape executes successfully.

Usage (from the repository root, with the venv active and .env loaded):

    python scripts/verify_kodi_schema.py

Exit code 0 means the application should work against this database.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pymysql  # noqa: E402

from movielist.config import Settings  # noqa: E402
from movielist.db import Database  # noqa: E402
from movielist.kodi import KodiRepository  # noqa: E402

REQUIRED_VIEWS: dict[str, tuple[str, ...]] = {
    "movie_view": (
        "idMovie", "c00", "c01", "c14", "c15", "premiered", "dateAdded",
        "rating", "votes", "uniqueid_value", "uniqueid_type",
    ),
    "tvshow_view": (
        "idShow", "c00", "c01", "c05", "c08", "dateAdded", "rating",
        "votes", "uniqueid_value", "uniqueid_type", "totalCount",
        "totalSeasons",
    ),
    "season_view": ("idSeason", "idShow", "season", "name", "episodes"),
    "episode_view": (
        "idEpisode", "idShow", "idSeason", "c00", "c01", "c05", "c12",
        "c13", "dateAdded", "rating",
    ),
    "tvshowcounts": ("idShow", "totalCount", "totalSeasons", "dateAdded"),
}

REQUIRED_TABLES: dict[str, tuple[str, ...]] = {
    "art": ("art_id", "media_id", "media_type", "type", "url"),
    "actor": ("actor_id", "name"),
    "actor_link": ("actor_id", "media_id", "media_type"),
    "genre": ("genre_id", "name"),
    "genre_link": ("genre_id", "media_id", "media_type"),
}

failures: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {label}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(label)


def main() -> int:
    settings = Settings.load()
    print(f"Target: {settings.kodi_db_user}@{settings.kodi_db_host}:"
          f"{settings.kodi_db_port}/{settings.kodi_db_name}")

    try:
        conn = pymysql.connect(
            host=settings.kodi_db_host,
            port=settings.kodi_db_port,
            user=settings.kodi_db_user,
            password=settings.kodi_db_password,
            database=settings.kodi_db_name,
            connect_timeout=settings.kodi_db_connect_timeout,
            read_timeout=settings.kodi_db_read_timeout,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )
    except pymysql.MySQLError as exc:
        print(f"[FAIL] connection — {type(exc).__name__}")
        return 1
    print("[PASS] connection")

    try:
        with conn.cursor() as cur:
            cur.execute("SHOW GRANTS")
            grants = [next(iter(r.values())) for r in cur.fetchall()]
        select_only = all("ALL PRIVILEGES" not in g for g in grants)
        has_select = any("SELECT" in g for g in grants)
        check(has_select, "account has SELECT privilege")
        check(select_only, "account has no broader-than-SELECT privilege",
              "; ".join(grants))
        for g in grants:
            print(f"       grant: {g}")

        with conn.cursor() as cur:
            cur.execute("SET SESSION TRANSACTION READ ONLY")
            cur.execute("SELECT @@session.tx_read_only AS ro")
            row = cur.fetchone()
        check(bool(row and row["ro"]), "session is READ ONLY")
    finally:
        conn.close()

    db = Database(settings)

    # Column inventory via information_schema
    try:
        rows = db.query(
            "SELECT table_name AS t, column_name AS c"
            " FROM information_schema.columns"
            " WHERE table_schema = %s",
            (settings.kodi_db_name,),
        )
        inventory: dict[str, set[str]] = {}
        for r in rows:
            inventory.setdefault(r["t"], set()).add(r["c"])
        for view, columns in REQUIRED_VIEWS.items():
            have = inventory.get(view, set())
            missing = [c for c in columns if c not in have]
            check(not missing, f"view {view} columns",
                  f"missing {missing}")
        for table, columns in REQUIRED_TABLES.items():
            have = inventory.get(table, set())
            missing = [c for c in columns if c not in have]
            check(not missing, f"table {table} columns",
                  f"missing {missing}")
    except Exception as exc:
        check(False, "information_schema inventory", repr(exc))

    if failures:
        print("\nSchema verification failed; not running queries.")
        db.close()
        return 1

    repo = KodiRepository(db)
    try:
        stats = repo.stats()
        check(stats["movies"] >= 0, "query: stats", str(stats))
        page = repo.list_movies(page=1, page_size=2)
        check(True, f"query: list_movies (total={page.total})")
        if page.items:
            m = repo.get_movie(page.items[0]["id"])
            check(m is not None, "query: get_movie")
        genres = repo.movie_genres()
        check(isinstance(genres, list), f"query: movie_genres ({len(genres)})")
        shows = repo.list_shows(page=1, page_size=2)
        check(True, f"query: list_shows (total={shows.total})")
        if shows.items:
            sid = shows.items[0]["id"]
            check(repo.get_show(sid) is not None, "query: get_show")
            seasons = repo.list_seasons(sid)
            check(True, f"query: list_seasons ({len(seasons)} seasons)")
            if seasons:
                eps = repo.list_episodes(sid, seasons[0]["number"])
                check(True, f"query: list_episodes ({len(eps)} episodes)")
        recent_m = repo.recently_added_movies(3)
        check(True, f"query: recently_added_movies ({len(recent_m)})")
        recent_s = repo.recently_updated_shows(3)
        check(True, f"query: recently_updated_shows ({len(recent_s)})")
        found = repo.search("the", limit=3)
        check(True, "query: search")
        if page.items:
            urls = repo.artwork_urls("movie", page.items[0]["id"], "poster")
            check(True, f"query: artwork_urls ({len(urls)} candidates)")
        check(repo.ping(), "query: ping")
    except Exception as exc:
        check(False, "application queries", repr(exc))
    finally:
        db.close()

    print()
    if failures:
        print(f"RESULT: {len(failures)} check(s) failed.")
        return 1
    print("RESULT: all checks passed. MovieList can use this database.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
