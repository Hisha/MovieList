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
DB_PATH = "movies.db"

# -------------------------
# Initialize Database
# -------------------------
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

# -------------------------
# Parse NFO File
# -------------------------
def parse_nfo(nfo_path):
    genres = []
    actors = []
    try:
        with open(nfo_path, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "xml")  # Use XML parser
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
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Get current movies in DB
    cur.execute("SELECT folder FROM movies")
    existing_movies = {row[0] for row in cur.fetchall()}

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

        # Insert only if not in DB
        if folder not in existing_movies:
            cur.execute("""
                INSERT INTO movies (title, folder, poster, genres, actors, added_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                title,
                folder,
                poster_path,
                genres,
                actors,
                time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(added_at))
            ))
            logging.info(f"Added new movie: {title}")

    # Remove DB entries for folders that no longer exist
    for old_folder in existing_movies - found_folders:
        cur.execute("DELETE FROM movies WHERE folder=?", (old_folder,))
        logging.info(f"Removed missing movie: {old_folder}")

    conn.commit()
    conn.close()
    logging.info("Rescan completed.")

if __name__ == "__main__":
    rescan_movies()
