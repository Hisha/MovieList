from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import sqlite3
import os
import sys
from urllib.parse import unquote

# === Config ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "movies.db")
STATIC_DIR = os.path.join(BASE_DIR, "static")
POSTER_FALLBACK = os.path.join(STATIC_DIR, "no-poster.png")
MOVIE_PATH = os.getenv("MOVIE_PATH", "/mnt/Movies")

# === App Setup ===
app = FastAPI(root_path="/ML")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory="templates")

print(">>> DEBUG: MovieList FastAPI starting...", file=sys.stdout)
sys.stdout.flush()


# === DB Helper ===
def get_db():
    return sqlite3.connect(DB_PATH)


# === Home Page (First 100 Movies) ===
@app.get("/", response_class=HTMLResponse)
async def home(request: Request, search: str = None, genre: str = None, actor: str = None, page: int = 1):
    conn = get_db()
    cur = conn.cursor()

    limit = 100
    offset = (page - 1) * limit

    query = "SELECT id, title, folder, poster, genres, actors FROM movies WHERE 1=1"
    params = []
    if search:
        query += " AND title LIKE ?"
        params.append(f"%{search}%")
    if genre:
        query += " AND genres LIKE ?"
        params.append(f"%{genre}%")
    if actor:
        query += " AND actors LIKE ?"
        params.append(f"%{actor}%")
    query += " ORDER BY added_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cur.execute(query, params)
    movies = cur.fetchall()

    # Filters
    cur.execute("SELECT DISTINCT genres FROM movies WHERE genres IS NOT NULL")
    genres_raw = cur.fetchall()
    genre_list = sorted({g.strip() for row in genres_raw for g in (row[0].split(",") if row[0] else []) if g.strip()})

    cur.execute("SELECT DISTINCT actors FROM movies WHERE actors IS NOT NULL")
    actors_raw = cur.fetchall()
    actor_list = sorted({a.strip() for row in actors_raw for a in (row[0].split(",") if row[0] else []) if a.strip()})

    conn.close()

    print(f"[DEBUG] Home loaded: page={page}, movies_returned={len(movies)}", file=sys.stdout)
    sys.stdout.flush()

    return templates.TemplateResponse("index.html", {
        "request": request,
        "movies": movies,
        "genres": genre_list,
        "actors": actor_list,
        "current_page": page
    })


# === JSON API for Load More (AJAX) ===
@app.get("/movies")
async def get_movies(page: int = 1, search: str = None, genre: str = None, actor: str = None):
    conn = get_db()
    cur = conn.cursor()

    limit = 100
    offset = (page - 1) * limit

    query = "SELECT id, title, folder, poster, genres, actors FROM movies WHERE 1=1"
    params = []
    if search:
        query += " AND title LIKE ?"
        params.append(f"%{search}%")
    if genre:
        query += " AND genres LIKE ?"
        params.append(f"%{genre}%")
    if actor:
        query += " AND actors LIKE ?"
        params.append(f"%{actor}%")
    query += " ORDER BY added_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cur.execute(query, params)
    movies = cur.fetchall()
    conn.close()

    print(f"[DEBUG] API /movies: page={page}, count={len(movies)}", file=sys.stdout)
    sys.stdout.flush()

    data = [
        {
            "id": m[0],
            "title": m[1],
            "poster": f"/ML/poster/{m[0]}",
            "genres": m[4] or "",
            "actors": m[5] or ""
        }
        for m in movies
    ]
    return JSONResponse({"movies": data})


# === Serve Poster Files ===
@app.get("/poster/{movie_id}")
async def serve_poster(movie_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT poster FROM movies WHERE id=?", (movie_id,))
    row = cur.fetchone()
    conn.close()

    if not row or not row[0]:
        print(f"[DEBUG] Poster missing for movie_id={movie_id}", file=sys.stdout)
        sys.stdout.flush()
        return FileResponse(POSTER_FALLBACK)

    poster_path = os.path.join(MOVIE_PATH, row[0])
    print(f"[DEBUG] Serving poster for movie_id={movie_id}, path={poster_path}", file=sys.stdout)
    sys.stdout.flush()

    if os.path.exists(poster_path):
        return FileResponse(poster_path)
    else:
        print(f"[DEBUG] Poster not found on disk. Fallback used for {movie_id}", file=sys.stdout)
        sys.stdout.flush()
        return FileResponse(POSTER_FALLBACK)
