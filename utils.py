import os
import sqlite3
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
MOVIE_PATH = os.getenv("MOVIE_PATH", "/mnt/Movies")
DB_PATH = os.getenv("DATABASE_PATH", "./movies.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS movies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        year TEXT,
        folder TEXT,
        poster TEXT,
        genres TEXT,
        actors TEXT,
        plot TEXT,
        added_at TEXT
    )''')
    conn.commit()
    conn.close()

def parse_nfo(nfo_path):
    """Extract metadata from NFO file using lxml."""
    try:
        with open(nfo_path, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "lxml")
            title = soup.find("title").text if soup.find("title") else "Unknown"
            year = soup.find("year").text if soup.find("year") else ""
            plot = soup.find("plot").text if soup.find("plot") else ""
            genres = ", ".join([g.text for g in soup.find_all("genre")])
            actors = ", ".join([a.find("name").text for a in soup.find_all("actor") if a.find("name")])
            return title, year, plot, genres, actors
    except Exception:
        return None, None, None, None, None

def scan_movies():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    for folder_name in sorted(os.listdir(MOVIE_PATH)):
        folder_path = os.path.join(MOVIE_PATH, folder_name)
        if not os.path.isdir(folder_path):
            continue
        poster_path = os.path.join(folder_path, "poster.jpg")
        nfo_path = os.path.join(folder_path, "movie.nfo")
        title, year, plot, genres, actors = parse_nfo(nfo_path) if os.path.exists(nfo_path) else (folder_name, "", "", "", "")
        cur.execute("SELECT id FROM movies WHERE folder=?", (folder_path,))
        if cur.fetchone():
            continue
        cur.execute("INSERT INTO movies (title, year, folder, poster, genres, actors, plot, added_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (title, year, folder_path, poster_path if os.path.exists(poster_path) else None, genres, actors, plot, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_movies(search=None, genre=None, actor=None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
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
    cur.execute(query, params)
    movies = cur.fetchall()
    conn.close()
    return movies

def get_filters():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT genres, actors FROM movies")
    genres_set = set()
    actors_set = set()
    for row in cur.fetchall():
        if row[0]:
            genres_set.update([g.strip() for g in row[0].split(",") if g.strip()])
        if row[1]:
            actors_set.update([a.strip() for a in row[1].split(",") if a.strip()])
    conn.close()
    return sorted(genres_set), sorted(actors_set)
