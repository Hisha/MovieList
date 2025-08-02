import os
import sqlite3
from datetime import datetime
from bs4 import BeautifulSoup

DB_PATH = "movies.db"

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
    except Exception as e:
        print(f"[WARN] Failed to parse NFO {nfo_path}: {e}")
        return None, None, None

def scan_movies(base_path="/mnt/Movies"):
    movies = []
    for folder_name in os.listdir(base_path):
        folder_path = os.path.join(base_path, folder_name)
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
