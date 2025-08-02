from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from urllib.parse import unquote
import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "movies.db")
POSTER_FALLBACK = os.path.join(BASE_DIR, "static/no-poster.png")

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

def get_db():
    return sqlite3.connect(DB_PATH)

@app.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    search: str = None,
    genre: str = None,
    actor: str = None,
    page: int = 1
):
    limit = 100
    offset = (page - 1) * limit

    conn = get_db()
    cur = conn.cursor()

    # Build dynamic query
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

    # Count for pagination
    count_query = "SELECT COUNT(*) FROM movies WHERE 1=1"
    count_params = []
    if search:
        count_query += " AND title LIKE ?"
        count_params.append(f"%{search}%")
    if genre:
        count_query += " AND genres LIKE ?"
        count_params.append(f"%{genre}%")
    if actor:
        count_query += " AND actors LIKE ?"
        count_params.append(f"%{actor}%")
    cur.execute(count_query, count_params)
    total_movies = cur.fetchone()[0]
    total_pages = (total_movies // limit) + (1 if total_movies % limit else 0)

    # Dropdown filters
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
        "page": page,
        "total_pages": total_pages
    })

@app.get("/poster/{movie_id}")
async def serve_poster(movie_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT folder FROM movies WHERE id=?", (movie_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return FileResponse(POSTER_FALLBACK)

    folder_path = row[0]
    poster_path = os.path.join(folder_path, "poster.jpg")
    if os.path.exists(poster_path):
        return FileResponse(poster_path)
    return FileResponse(POSTER_FALLBACK)
