import os
import sqlite3
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
from utils import scan_movies, get_movies, get_filters

load_dotenv()

app = FastAPI()

MOVIE_PATH = os.getenv("MOVIE_PATH", "/mnt/Movies")
DB_PATH = os.getenv("DATABASE_PATH", "movies.db")

# ✅ Mount posters folder
app.mount("/posters", StaticFiles(directory=MOVIE_PATH), name="posters")

templates = Jinja2Templates(directory="templates")

# ✅ Initialize DB on startup
@app.on_event("startup")
async def startup_event():
    if not os.path.exists(DB_PATH):
        print("[INFO] Creating database and scanning movies...")
        scan_movies(MOVIE_PATH, DB_PATH)

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, genre: str = None, actor: str = None, search: str = None):
    movies = get_movies(DB_PATH, genre, actor, search)
    genres, actors = get_filters(DB_PATH)
    return templates.TemplateResponse("index.html", {
        "request": request,
        "movies": movies,
        "genres": genres,
        "actors": actors,
        "selected_genre": genre,
        "selected_actor": actor,
        "search_query": search
    })

@app.post("/rescan")
async def rescan():
    scan_movies(MOVIE_PATH, DB_PATH)
    return RedirectResponse("/", status_code=303)
