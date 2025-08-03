from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import sqlite3
import os
import sys
from html import escape

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

# === Sort Mapping ===
SORT_MAP = {
    "newest": "added_at DESC",
    "oldest": "added_at ASC",
    "az": "title ASC",
    "za": "title DESC"
}

# === Home Page ===
@app.get("/", response_class=HTMLResponse)
async def home(request: Request, search: str = None, genre: str = None, actor: str = None, sort: str = "newest", page: int = 1):
    conn = get_db()
    cur = conn.cursor()

    limit = 100
    offset = (page - 1) * limit
    sort_order = SORT_MAP.get(sort, "added_at DESC")

    query = f"SELECT id, title, folder, poster, genres, actors FROM movies WHERE 1=1"
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
    query += f" ORDER BY {sort_order} LIMIT ? OFFSET ?"
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

    return templates.TemplateResponse("index.html", {
        "request": request,
        "movies": movies,
        "genres": genre_list,
        "actors": actor_list,
        "current_page": page,
        "sort": sort
    })

# === API for AJAX Pagination ===
@app.get("/movies")
async def get_movies(page: int = 1, search: str = None, genre: str = None, actor: str = None, sort: str = "newest"):
    conn = get_db()
    cur = conn.cursor()

    limit = 100
    offset = (page - 1) * limit
    sort_order = SORT_MAP.get(sort, "added_at DESC")

    query = f"SELECT id, title, folder, poster, genres, actors FROM movies WHERE 1=1"
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
    query += f" ORDER BY {sort_order} LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cur.execute(query, params)
    movies = cur.fetchall()
    conn.close()

    data = [
        {
            "id": m[0],
            "title": escape(m[1] or ""),
            "poster": f"/ML/poster/{m[0]}",
            "genres": escape(m[4] or "N/A"),
            "actors": escape(m[5] or "N/A")
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
        return FileResponse(POSTER_FALLBACK)

    poster_path = os.path.join(MOVIE_PATH, row[0])
    if os.path.exists(poster_path):
        return FileResponse(poster_path)
    else:
        return FileResponse(POSTER_FALLBACK)
