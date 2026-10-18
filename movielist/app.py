"""FastAPI application: MovieList 2.0 read-only Kodi catalog."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__
from .artwork import ART_TYPES, MEDIA_TYPES, ArtworkCache, UnsafeArtworkSource
from .config import Settings
from .db import Database, DatabaseUnavailable
from .kodi import KodiRepository, MOVIE_SORTS, SHOW_SORTS
from .ttlcache import TTLCache

log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent


def _clean_sort(sort: str | None, allowed: dict[str, str], default: str) -> str:
    return sort if sort in allowed else default


def _clean_page(page: int | None) -> int:
    try:
        page = int(page or 1)
    except (TypeError, ValueError):
        return 1
    return min(max(page, 1), 100_000)


def _clean_str(value: str | None, max_len: int = 200) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    return value[:max_len]


def create_app(
    settings: Settings | None = None,
    repo: KodiRepository | None = None,
    artwork: ArtworkCache | None = None,
) -> FastAPI:
    settings = settings or Settings.load()
    if repo is None:
        db = Database(settings)
        repo = KodiRepository(db)
    if artwork is None:
        artwork = ArtworkCache(settings, repo)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        try:
            repo.close()
        except Exception:
            pass

    app = FastAPI(title="MovieList", version=__version__, root_path=settings.root_path,
                  lifespan=lifespan)
    app.state.settings = settings
    app.state.repo = repo
    app.state.artwork = artwork

    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
    templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

    stats_cache = TTLCache(300)
    genres_cache = TTLCache(600)

    def movie_genres() -> list[str]:
        return genres_cache.get_or_set("movie", repo.movie_genres)

    def show_genres() -> list[str]:
        return genres_cache.get_or_set("tvshow", repo.show_genres)

    def context(request: Request, active: str = "", **extra: Any) -> dict[str, Any]:
        root = request.scope.get("root_path", "") or ""
        return {
            "request": request,
            "root": root,
            "version": __version__,
            "active": active,
            **extra,
        }

    # -- error handling ----------------------------------------------------

    @app.exception_handler(DatabaseUnavailable)
    async def db_unavailable_handler(
        request: Request, exc: DatabaseUnavailable
    ):
        log.error("Database unavailable: %s", exc)
        if request.url.path.startswith("/api") or request.url.path.startswith(
            "/healthz"
        ):
            return JSONResponse(
                {"status": "error", "detail": "database unavailable"},
                status_code=503,
            )
        return templates.TemplateResponse(
            request,
            "error.html",
            context(
                request,
                title="Service Temporarily Unavailable",
                message="The media library database is currently unreachable. "
                "Please try again later.",
            ),
            status_code=503,
        )

    @app.exception_handler(UnsafeArtworkSource)
    async def unsafe_artwork_handler(_: Request, exc: UnsafeArtworkSource):
        return JSONResponse(
            {"status": "error", "detail": "invalid artwork request"},
            status_code=400,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ):
        if exc.status_code == 404:
            return templates.TemplateResponse(
                request,
                "error.html",
                context(
                    request,
                    title="Not Found",
                    message="The requested page does not exist.",
                ),
                status_code=404,
            )
        return templates.TemplateResponse(
            request,
            "error.html",
            context(
                request,
                title="Error",
                message="Something went wrong.",
            ),
            status_code=exc.status_code,
        )

    # -- pages ---------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request):
        def load_stats() -> dict[str, int]:
            return repo.stats()

        def load_recent_movies() -> list[dict[str, Any]]:
            return repo.recently_added_movies(settings.recent_count)

        def load_recent_shows() -> list[dict[str, Any]]:
            return repo.recently_updated_shows(settings.recent_count)

        stats = stats_cache.get_or_set("stats", load_stats)
        recent_movies = load_recent_movies()
        recent_shows = load_recent_shows()
        return templates.TemplateResponse(
            request,
            "home.html",
            context(
                request,
                active="home",
                stats=stats,
                recent_movies=recent_movies,
                recent_shows=recent_shows,
                page_size=settings.page_size,
            ),
        )

    @app.get("/movies", response_class=HTMLResponse)
    async def movies_page(
        request: Request,
        q: str | None = None,
        genre: str | None = None,
        sort: str | None = None,
        page: int = 1,
    ):
        q = _clean_str(q)
        genre = _clean_str(genre, 100)
        sort = _clean_sort(sort, MOVIE_SORTS, "newest")
        page = _clean_page(page)
        result = repo.list_movies(
            search=q,
            genre=genre,
            sort=sort,
            page=page,
            page_size=settings.page_size,
        )
        return templates.TemplateResponse(
            request,
            "movies.html",
            context(
                request,
                active="movies",
                result=result,
                q=q or "",
                genre=genre or "",
                sort=sort,
                genres=movie_genres(),
                page_size=settings.page_size,
            ),
        )

    @app.get("/api/movies")
    async def movies_api(
        request: Request,
        q: str | None = None,
        genre: str | None = None,
        sort: str | None = None,
        page: int = 1,
    ):
        q = _clean_str(q)
        genre = _clean_str(genre, 100)
        sort = _clean_sort(sort, MOVIE_SORTS, "newest")
        page = _clean_page(page)
        result = repo.list_movies(
            search=q,
            genre=genre,
            sort=sort,
            page=page,
            page_size=settings.page_size,
        )
        root = request.scope.get("root_path", "") or ""
        items = [
            {
                "id": m["id"],
                "title": m["title"],
                "year": m["year"],
                "rating": m["rating"],
                "url": f"{root}/movies/{m['id']}",
                "poster": f"{root}/art/movie/{m['id']}/poster",
            }
            for m in result.items
        ]
        return {
            "items": items,
            "page": result.page,
            "pages": result.pages,
            "total": result.total,
            "has_next": result.has_next,
        }

    @app.get("/movies/{movie_id}", response_class=HTMLResponse)
    async def movie_detail(request: Request, movie_id: int):
        movie = repo.get_movie(movie_id)
        if movie is None:
            raise HTTPException(status_code=404)
        has_fanart = bool(repo.artwork_urls("movie", movie_id, "fanart", limit=1))
        return templates.TemplateResponse(
            request,
            "movie.html",
            context(request, active="movie", movie=movie,
                    has_fanart=has_fanart),
        )

    @app.get("/shows", response_class=HTMLResponse)
    async def shows_page(
        request: Request,
        q: str | None = None,
        genre: str | None = None,
        sort: str | None = None,
        page: int = 1,
    ):
        q = _clean_str(q)
        genre = _clean_str(genre, 100)
        sort = _clean_sort(sort, SHOW_SORTS, "az")
        page = _clean_page(page)
        result = repo.list_shows(
            search=q,
            genre=genre,
            sort=sort,
            page=page,
            page_size=settings.shows_page_size,
        )
        return templates.TemplateResponse(
            request,
            "shows.html",
            context(
                request,
                active="shows",
                result=result,
                q=q or "",
                genre=genre or "",
                sort=sort,
                genres=show_genres(),
                page_size=settings.shows_page_size,
            ),
        )

    @app.get("/api/shows")
    async def shows_api(
        request: Request,
        q: str | None = None,
        genre: str | None = None,
        sort: str | None = None,
        page: int = 1,
    ):
        q = _clean_str(q)
        genre = _clean_str(genre, 100)
        sort = _clean_sort(sort, SHOW_SORTS, "az")
        page = _clean_page(page)
        result = repo.list_shows(
            search=q,
            genre=genre,
            sort=sort,
            page=page,
            page_size=settings.shows_page_size,
        )
        root = request.scope.get("root_path", "") or ""
        items = [
            {
                "id": s["id"],
                "title": s["title"],
                "year": s["year"],
                "rating": s["rating"],
                "season_count": s["season_count"],
                "episode_count": s["episode_count"],
                "url": f"{root}/shows/{s['id']}",
                "poster": f"{root}/art/tvshow/{s['id']}/poster",
            }
            for s in result.items
        ]
        return {
            "items": items,
            "page": result.page,
            "pages": result.pages,
            "total": result.total,
            "has_next": result.has_next,
        }

    @app.get("/shows/{show_id}", response_class=HTMLResponse)
    async def show_detail(request: Request, show_id: int, season: int | None = None):
        show = repo.get_show(show_id)
        if show is None:
            raise HTTPException(status_code=404)
        seasons = repo.list_seasons(show_id)
        active_season = None
        if seasons:
            wanted = season
            for s in seasons:
                if wanted is not None and s["number"] == wanted:
                    active_season = s
                    break
            if active_season is None:
                # Prefer the first regular season with cataloged episodes,
                # then any season with episodes, then the first season.
                active_season = next(
                    (s for s in seasons
                     if s["number"] > 0 and s["episode_count"] > 0),
                    None,
                ) or next(
                    (s for s in seasons if s["episode_count"] > 0),
                    seasons[0],
                )
        episodes = (
            repo.list_episodes(show_id, active_season["number"])
            if active_season
            else []
        )
        has_fanart = bool(repo.artwork_urls("tvshow", show_id, "fanart", limit=1))
        return templates.TemplateResponse(
            request,
            "show.html",
            context(
                request,
                active="show",
                show=show,
                seasons=seasons,
                active_season=active_season,
                episodes=episodes,
                has_fanart=has_fanart,
            ),
        )

    @app.get("/api/shows/{show_id}/seasons/{season}")
    async def season_episodes_api(show_id: int, season: int):
        show = repo.get_show(show_id)
        if show is None:
            raise HTTPException(status_code=404)
        episodes = repo.list_episodes(show_id, season)
        return {
            "show_id": show_id,
            "season": season,
            "episodes": episodes,
        }

    @app.get("/search", response_class=HTMLResponse)
    async def search_page(request: Request, q: str | None = None):
        q = _clean_str(q) or ""
        results: dict[str, list[dict[str, Any]]] = {"movies": [], "shows": []}
        if q:
            results = repo.search(q, limit=12)
        return templates.TemplateResponse(
            request,
            "search.html",
            context(request, active="search", q=q, results=results),
        )

    # -- artwork ---------------------------------------------------------------

    @app.get("/art/{media_type}/{media_id}/{art_type}")
    async def artwork_endpoint(
        request: Request,
        media_type: str,
        media_id: int,
        art_type: str,
    ):
        if media_type not in MEDIA_TYPES or art_type not in ART_TYPES:
            raise HTTPException(status_code=404)
        result = artwork.get(media_type, media_id, art_type)
        if_none_match = request.headers.get("if-none-match")
        if if_none_match and if_none_match == result.etag:
            return Response(status_code=304, headers={"ETag": result.etag})
        return FileResponse(
            result.path,
            media_type=result.content_type,
            headers={
                "Cache-Control": "private, max-age=3600",
                "ETag": result.etag,
            },
        )

    # -- health -----------------------------------------------------------------

    @app.get("/healthz")
    async def healthz():
        if repo.ping():
            return {"status": "ok"}
        return JSONResponse({"status": "degraded"}, status_code=503)

    return app
