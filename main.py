import os
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from database import SessionLocal, init_db
from utils import scan_movies
import models

load_dotenv()

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

MOVIES_PATH = os.getenv("MOVIES_PATH", "/mnt/Movies")
DATABASE_PATH = os.getenv("DATABASE_PATH", "movielist.db")

# Initialize DB
init_db()

@app.get("/", response_class=HTMLResponse)
def home(request: Request, search: str = "", genre: str = "", actor: str = ""):
    db: Session = SessionLocal()
    query = db.query(models.Movie)

    if search:
        query = query.filter(models.Movie.title.ilike(f"%{search}%"))
    if genre:
        query = query.join(models.Movie.genres).filter(models.Genre.name == genre)
    if actor:
        query = query.join(models.Movie.actors).filter(models.Actor.name == actor)

    movies = query.order_by(models.Movie.date_added.desc()).all()

    genres = db.query(models.Genre.name).distinct().all()
    actors = db.query(models.Actor.name).distinct().all()
    db.close()

    return templates.TemplateResponse("index.html", {
        "request": request,
        "movies": movies,
        "genres": [g[0] for g in genres],
        "actors": [a[0] for a in actors],
        "search": search,
        "genre": genre,
        "actor": actor
    })

@app.post("/rescan")
def rescan_movies():
    db: Session = SessionLocal()
    added_count = scan_movies(MOVIES_PATH, db)
    db.close()
    return JSONResponse({"message": f"Rescan complete. {added_count} movies updated."})

@app.get("/details/{movie_id}")
def get_movie_details(movie_id: int):
    db: Session = SessionLocal()
    movie = db.query(models.Movie).filter(models.Movie.id == movie_id).first()
    db.close()
    if not movie:
        return JSONResponse({"error": "Movie not found"}, status_code=404)
    return {
        "title": movie.title,
        "year": movie.year,
        "genres": [g.name for g in movie.genres],
        "actors": [a.name for a in movie.actors],
        "file_path": movie.file_path
    }
