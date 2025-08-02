import os
import sqlite3
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from urllib.parse import unquote

load_dotenv()
MOVIE_PATH = os.getenv("MOVIE_PATH", "/mnt/Movies")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "movies.db")
POSTER_FALLBACK = os.path.join(BASE_DIR, "static/no-poster.png")

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

def get_db():
    return sqlite3.connect(DB_PATH)

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, search: str = None, genre: str = None, actor: str = None, page: int = 1):
    conn = get_db()
    cur = conn.cursor()

    per_page = 100
    offset = (page - 1) * per_page

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
    params.extend([per_page, offset])

    cur.execute(query, params)
    movies = cur.fetchall()

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
        "page": page
    })

@app.get("/poster/{movie_id}")
async def serve_poster(movie_id: int):
    print(f"[DEBUG] Received request for poster of movie_id: {movie_id}")
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT poster FROM movies WHERE id=?", (movie_id,))
    row = cur.fetchone()
    conn.close()

    if not row or not row[0]:
        print(f"[DEBUG] No poster found in DB for movie_id: {movie_id}. Using fallback: {POSTER_FALLBACK}")
        if os.path.exists(POSTER_FALLBACK):
            return FileResponse(POSTER_FALLBACK)
        print(f"[ERROR] Fallback poster does not exist at {POSTER_FALLBACK}")
        raise HTTPException(status_code=404, detail="Poster not found")

    poster_relative = row[0]
    poster_path = os.path.join(MOVIE_PATH, poster_relative)

    print(f"[DEBUG] DB poster path: {poster_relative}")
    print(f"[DEBUG] Resolved full path: {poster_path}")
    print(f"[DEBUG] Checking if file exists at: {poster_path}")

    if os.path.exists(poster_path):
        print(f"[DEBUG] Serving poster from: {poster_path}")
        return FileResponse(poster_path)
    else:
        print(f"[WARN] Poster file not found at {poster_path}, using fallback.")
        if os.path.exists(POSTER_FALLBACK):
            return FileResponse(POSTER_FALLBACK)
        print(f"[ERROR] Fallback poster does not exist at {POSTER_FALLBACK}")
        raise HTTPException(status_code=404, detail="Poster not found")

