import os
import sqlite3
from datetime import datetime
from bs4 import BeautifulSoup

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "movies.db")
MOVIE_DIR = os.getenv("MOVIE_DIR", "/mnt/Movies")  # From .env later

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS movies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        folder TEXT,
        poster TEXT,
        genres TEXT,
        actors TEXT,
        added_at TEXT
    )
    """)
    conn.commit()
    conn.close()

def extract_metadata(nfo_path):
    genres, actors = "", ""
    try:
        with open(nfo_path, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "lxml")
            genres = ", ".join([g.text for g in soup.find_all("genre")]) or ""
            actors = ", ".join([a.text for a in soup.find_all("actor")]) or ""
    except Exception as e:
        print(f"[WARN] Failed to parse {nfo_path}: {e}")
    return genres, actors

def scan_movies():
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    for folder in os.listdir(MOVIE_DIR):
        folder_path = os.path.join(MOVIE_DIR, folder)
        if not os.path.isdir(folder_path):
            continue

        # Check if exists
        cur.execute("SELECT id FROM movies WHERE folder = ?", (folder_path,))
        if cur.fetchone():
            continue  # Skip if already in DB

        title = folder
        poster_path = os.path.join(folder_path, "poster.jpg")
        if not os.path.exists(poster_path):
            poster_path = None

        nfo_path = os.path.join(folder_path, "movie.nfo")
        genres, actors = extract_metadata(nfo_path) if os.path.exists(nfo_path) else ("", "")

        cur.execute("""
        INSERT INTO movies (title, folder, poster, genres, actors, added_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (title, folder_path, poster_path, genres, actors, datetime.now().isoformat()))

    conn.commit()
    conn.close()
