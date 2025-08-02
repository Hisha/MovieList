from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import sqlite3
import os
from urllib.parse import unquote

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "movies.db")
POSTER_FALLBACK = "/static/no-poster.png"

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

def get_db():
    return sqlite3.connect(DB_PATH)

@app.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    search: str = Query(None),
    genre: str = Query(None),
    actor: str = Query(None),
    page: int = Query(1, ge=1)
):
    limit = 100
    offset = (page - 1) * limit

    conn = get_db()
    cur = conn.cursor()

    # Build query with filters
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

    # Total count for pagination
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

    # Fetch genres & actors for dropdowns
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

@app.get("/poster/{path:path}")
async def poster_proxy(path: str):
    file_path = unquote(path)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    return FileResponse("static/no-poster.png")
