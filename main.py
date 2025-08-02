from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import sqlite3
import os
import sys

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

# === Home Page ===
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

    return templates.TemplateResponse("index.html", {
        "request": request,
        "movies": movies,
        "genres": genre_list,
        "actors": actor_list,
        "current_page": page
    })

# === Load More Route for AJAX ===
@app.get("/load_more", response_class=HTMLResponse)
async def load_more(request: Request, page: int = Query(1), search: str = None, genre: str = None, actor: str = None):
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

    html_snippet = ""
    for movie in movies:
        html_snippet += f"""
        <div class="col-6 col-md-3 mb-4">
            <div class="movie-card" onclick="showDetails('{movie[1]}', '/ML/poster/{movie[0]}', '{movie[4] or 'N/A'}', '{movie[5] or 'N/A'}')">
                <img src="/ML/poster/{movie[0]}" alt="{movie[1]}">
                <div class="p-2 text-center">
                    <h6>{movie[1]}</h6>
                </div>
            </div>
        </div>
        """
    return HTMLResponse(content=html_snippet)

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
