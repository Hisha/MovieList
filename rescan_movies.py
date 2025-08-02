import os
import sqlite3
from datetime import datetime
from bs4 import BeautifulSoup

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MOVIE_DIR = "/mnt/Movies"
DB_PATH = os.path.join(BASE_DIR, "movies.db")

# Create table if not exists
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

def parse_nfo(nfo_path):
    genres, actors = [], []
    if os.path.exists(nfo_path):
        with open(nfo_path, "r", encoding="utf-8", errors="ignore") as f:
            soup = BeautifulSoup(f.read(), "xml")
            genres = [g.text for g in soup.find_all("genre")]
            actors = [a.find("name").text for a in soup.find_all("actor")]
    return ",".join(genres), ",".join(actors)

existing_folders = {row[0] for row in cur.execute("SELECT folder FROM movies").fetchall()}

added = 0
for folder in sorted(os.listdir(MOVIE_DIR)):
    full_path = os.path.join(MOVIE_DIR, folder)
    if not os.path.isdir(full_path) or folder in existing_folders:
        continue

    poster = os.path.join(full_path, "poster.jpg")
    nfo_file = os.path.join(full_path, "movie.nfo")
    genres, actors = parse_nfo(nfo_file)

    cur.execute("INSERT INTO movies (title, folder, poster, genres, actors, added_at) VALUES (?, ?, ?, ?, ?, ?)",
                (folder, full_path, poster if os.path.exists(poster) else None, genres, actors, datetime.now().isoformat()))
    added += 1

conn.commit()
conn.close()
print(f"✅ Rescan complete. {added} new movies added.")
