import os
import sqlite3
import time
from dotenv import load_dotenv
from bs4 import BeautifulSoup

# Load environment variables
load_dotenv()
MOVIE_PATH = os.getenv("MOVIE_PATH", "/mnt/Movies")
DB_PATH = "movies.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS movies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        folder TEXT,
        poster TEXT,
        genres TEXT,
        actors TEXT,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()
    conn.close()

def parse_nfo(nfo_path):
    genres = []
    actors = []
    try:
        with open(nfo_path, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "xml")  # Use XML parsing for NFO
            for genre_tag in soup.find_all("genre"):
                genres.append(genre_tag.get_text(strip=True))
            for actor_tag in soup.find_all("actor"):
                name_tag = actor_tag.find("name")
                if name_tag:
                    actors.append(name_tag.get_text(strip=True))
    except Exception as e:
        print(f"Failed to parse NFO {nfo_path}: {e}")
    return ",".join(genres), ",".join(actors)

def rescan_movies():
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    for folder in os.listdir(MOVIE_PATH):
        folder_path = os.path.join(MOVIE_PATH, folder)
        if not os.path.isdir(folder_path):
            continue

        title = folder
        poster_path = None
        nfo_path = None

        # Look for poster.jpg and .nfo file
        for file in os.listdir(folder_path):
            if file.lower() == "poster.jpg":
                poster_path = os.path.join(folder, file)  # relative path
            if file.lower().endswith(".nfo"):
                nfo_path = os.path.join(folder_path, file)

        genres, actors = ("", "")
        if nfo_path:
            genres, actors = parse_nfo(nfo_path)

        # Last modified timestamp for folder
        added_at = int(os.path.getmtime(folder_path))

        # Check if movie exists
        cur.execute("SELECT id FROM movies WHERE folder=?", (folder,))
        if cur.fetchone():
            continue

        # Insert new movie
        cur.execute("""
            INSERT INTO movies (title, folder, poster, genres, actors, added_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (title, folder, poster_path, genres, actors, time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(added_at))))
        print(f"Added: {title}")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    rescan_movies()
