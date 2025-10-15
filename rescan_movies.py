import os
import sqlite3
import time
import logging
from dotenv import load_dotenv
from bs4 import BeautifulSoup

# -------------------------
# Logging Configuration
# -------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

# -------------------------
# Load ENV and Setup Paths
# -------------------------
load_dotenv()
MOVIE_PATH = os.getenv("MOVIE_PATH", "/mnt/Movies")
DB_PATH = os.path.join(os.path.dirname(__file__), "movies.db")

# -------------------------
# Initialize Database
# -------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
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

# -------------------------
# Parse NFO File
# -------------------------
def parse_nfo(nfo_path):
    genres = []
    actors = []
    try:
        with open(nfo_path, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "xml")
            for genre_tag in soup.find_all("genre"):
                genres.append(genre_tag.get_text(strip=True))
            for actor_tag in soup.find_all("actor"):
                name_tag = actor_tag.find("name")
                if name_tag:
                    actors.append(name_tag.get_text(strip=True))
    except Exception as e:
        logging.error(f"Failed to parse NFO {nfo_path}: {e}")
    return ",".join(genres), ",".join(actors)

# -------------------------
# Main Rescan Logic
# -------------------------
def rescan_movies():
    logging.info(f"Starting rescan of movies in {MOVIE_PATH}")
    logging.info(f"Using database: {DB_PATH}")
    init_db()
    conn = sqlite3.connect(DB_PATH)

    # Set WAL again in case DB was already created
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")

    cur = conn.cursor()

    # Get current movies in DB
    cur.execute("SELECT folder FROM movies")
    existing_movies = {row[0].lower() for row in cur.fetchall()}

    # Track folders found in filesystem
    found_folders = set()

    for folder in os.listdir(MOVIE_PATH):
        folder_path = os.path.join(MOVIE_PATH, folder)
        if not os.path.isdir(folder_path):
            continue

        found_folders.add(folder)
        title = folder
        poster_path = None
        nfo_path = None

        for file in os.listdir(folder_path):
            if file.lower() == "poster.jpg":
                poster_path = os.path.join(folder, file)
            if file.lower().endswith(".nfo"):
                nfo_path = os.path.join(folder_path, file)

        genres, actors = "", ""
        if nfo_path:
            genres, actors = parse_nfo(nfo_path)

        added_at = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(os.path.getmtime(folder_path)))

        if folder.lower() not in existing_movies:
            cur.execute("""
                INSERT INTO movies (title, folder, poster, genres, actors, added_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (title, folder, poster_path, genres, actors, added_at))
            logging.info(f"Added new movie: {title}")
        else:
            cur.execute("""
                UPDATE movies SET poster=?, genres=?, actors=? WHERE folder=?
            """, (poster_path, genres, actors, folder))

    # Remove entries for missing folders
    for old_folder in existing_movies - {f.lower() for f in found_folders}:
        cur.execute("DELETE FROM movies WHERE lower(folder)=?", (old_folder,))
        logging.info(f"Removed missing movie: {old_folder}")

    conn.commit()
    conn.close()
    logging.info("Rescan completed.")

if __name__ == "__main__":
    rescan_movies()
