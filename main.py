import os
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
from utils import init_db, scan_movies, get_movies, get_filters

load_dotenv()
MOVIE_PATH = os.getenv("MOVIE_PATH", "/mnt/Movies")

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Initialize DB and initial scan
init_db()
scan_movies()

# Serve posters dynamically
@app.get("/poster/{movie_id}")
async def get_poster(movie_id: int):
    from utils import DB_PATH
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT poster FROM movies WHERE id=?", (movie_id,))
    row = cur.fetchone()
    conn.close()
    if row and row[0] and os.path.exists(row[0]):
        return FileResponse(row[0])
    return FileResponse("templates/no-poster.png")

@app.get("/")
def home(request: Request):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM movies ORDER BY added_at DESC")
    movies = c.fetchall()
    conn.close()
    return templates.TemplateResponse("index.html", {"request": request, "movies": movies})

@app.post("/rescan")
async def rescan():
    scan_movies()
    return {"status": "ok", "message": "Library rescanned successfully."}
