import os
from bs4 import BeautifulSoup
from models import Movie, Genre, Actor
from sqlalchemy.orm import Session
from datetime import datetime

def parse_nfo(nfo_path):
    genres = []
    actors = []
    year = ""
    try:
        with open(nfo_path, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "lxml")
            year_tag = soup.find("year")
            if year_tag:
                year = year_tag.text
            genres = [g.text for g in soup.find_all("genre")]
            actors = [a.text for a in soup.find_all("actor")]
    except:
        pass
    return year, genres, actors

def scan_movies(base_path, db: Session):
    added_count = 0
    for root, dirs, files in os.walk(base_path):
        if any(f.endswith(".mp4") for f in files):
            title = os.path.basename(root)
            movie = db.query(Movie).filter(Movie.title == title).first()
            if not movie:
                movie = Movie(title=title, file_path=root, date_added=datetime.utcnow())
            poster = [f for f in files if f.lower() == "poster.jpg"]
            if poster:
                movie.poster = os.path.join(root, poster[0])
            nfo_file = [f for f in files if f.endswith(".nfo")]
            if nfo_file:
                year, genres, actors = parse_nfo(os.path.join(root, nfo_file[0]))
                movie.year = year
                movie.genres = [get_or_create_genre(db, g) for g in genres]
                movie.actors = [get_or_create_actor(db, a) for a in actors]
            db.add(movie)
            added_count += 1
    db.commit()
    return added_count

def get_or_create_genre(db: Session, name: str):
    genre = db.query(Genre).filter(Genre.name == name).first()
    if not genre:
        genre = Genre(name=name)
        db.add(genre)
        db.commit()
    return genre

def get_or_create_actor(db: Session, name: str):
    actor = db.query(Actor).filter(Actor.name == name).first()
    if not actor:
        actor = Actor(name=name)
        db.add(actor)
        db.commit()
    return actor
