from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from urllib.parse import unquote
import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "movies.db")
POSTER_FALLBACK = os.path.join(BASE_DIR, "static", "no-poster.png")

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def get_db():
    return sqlite3.connect(DB_PATH)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request, search: str = None, genre: str = None, actor: str = None):
    conn = get_db()
    cur = conn.cursor()

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
    query += " ORDER BY added_at DESC"

    cur.execute(query, params)
    movies = cur.fetchall()

    # Filters
    cur.execute("SELECT genres FROM movies WHERE genres IS NOT NULL")
    genres_raw = cur.fetchall()
    genre_list = sorted({g.strip() for row in genres_raw for g in (row[0].split(",") if row[0] else []) if g.strip()})

    cur.execute("SELECT actors FROM movies WHERE actors IS NOT NULL")
    actors_raw = cur.fetchall()
    actor_list = sorted({a.strip() for row in actors_raw for a in (row[0].split(",") if row[0] else []) if a.strip()})

    conn.close()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "movies": movies,
        "genres": genre_list,
        "actors": actor_list
    })


@app.get("/posters/{path:path}")
async def poster_proxy(path: str):
    file_path = unquote(path)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    return FileResponse(POSTER_FALLBACK)
