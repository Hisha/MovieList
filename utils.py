import os
import sqlite3
from datetime import datetime
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()
MOVIE_PATH = os.getenv("MOVIE_PATH", "/mnt/Movies")
DB_PATH = os.getenv("DB_PATH", "movies.db")


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            folder TEXT UNIQUE,
            poster TEXT,
            genres TEXT,
            actors TEXT,
            added_at TEXT
        )
        """)
        conn.commit()


def parse_nfo(nfo_path):
    try:
        with open(nfo_path, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "lxml")
            title = soup.find("title").text if soup.find("title") else None
            genres = ", ".join([g.text for g in soup.find_all("genre")])
            actors = ", ".join([a.text for a in soup.find_all("actor")])
            return title, genres, actors
    except Exception:
        return None, None, None


def scan_movies():
    movies = []
    for folder_name in os.listdir(MOVIE_PATH):
        folder_path = os.path.join(MOVIE_PATH, folder_name)
        if not os.path.isdir(folder_path):
            continue

        poster_path = None
        for img_name in os.listdir(folder_path):
            if "poster" in img_name.lower() and (img_name.endswith(".jpg") or img_name.endswith(".png")):
                poster_path = os.path.join(folder_path, img_name)
                break

        nfo_file = next((f for f in os.listdir(folder_path) if f.endswith(".nfo")), None)
        title, genres, actors = (None, None, None)
        if nfo_file:
            title, genres, actors = parse_nfo(os.path.join(folder_path, nfo_file))

        added_at = datetime.utcfromtimestamp(os.path.getmtime(folder_path)).isoformat()

        movies.append({
            "folder": folder_path,
            "title": title or folder_name,
            "poster": poster_path,
            "genres": genres,
            "actors": actors,
            "added_at": added_at
        })
    return movies


def add_movie_to_db(movie):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("""
        INSERT OR IGNORE INTO movies (title, folder, poster, genres, actors, added_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (movie["title"], movie["folder"], movie["poster"], movie["genres"], movie["actors"], movie["added_at"]))
        conn.commit()


def get_movies(search=None, genre=None, actor=None):
    query = "SELECT * FROM movies WHERE 1=1"
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

    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute(query, params)
        return c.fetchall()


def get_all_genres():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT genres FROM movies")
        genres = set()
        for row in c.fetchall():
            if row[0]:
                for g in row[0].split(","):
                    genres.add(g.strip())
        return sorted(genres)


def get_all_actors():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT actors FROM movies")
        actors = set()
        for row in c.fetchall():
            if row[0]:
                for a in row[0].split(","):
                    actors.add(a.strip())
        return sorted(actors)
