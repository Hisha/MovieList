import os
import sqlite3
import logging
from dotenv import load_dotenv
from bs4 import BeautifulSoup

# Load environment variables
load_dotenv()
MOVIE_PATH = os.getenv("MOVIE_PATH")
DATABASE_PATH = os.getenv("DATABASE_PATH")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

def get_existing_movies(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS movies (id INTEGER PRIMARY KEY, title TEXT, folder TEXT UNIQUE, poster TEXT, genres TEXT, actors TEXT)")
    conn.commit()
    cursor.execute("SELECT folder FROM movies")
    existing = {row[0] for row in cursor.fetchall()}
    conn.close()
    return existing

def parse_nfo(nfo_path):
    try:
        with open(nfo_path, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "xml")
        title = soup.find("title").text if soup.find("title") else os.path.basename(os.path.dirname(nfo_path))
        genres = ", ".join([g.text for g in soup.find_all("genre")]) if soup.find("genre") else ""
        actors = ", ".join([a.text for a in soup.find_all("name")]) if soup.find("actor") else ""
        return title, genres, actors
    except Exception as e:
        logging.warning(f"Failed to parse NFO: {nfo_path} - {e}")
        return os.path.basename(os.path.dirname(nfo_path)), "", ""

def insert_movie(db_path, title, folder, poster, genres, actors):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO movies (title, folder, poster, genres, actors) VALUES (?, ?, ?, ?, ?)",
                   (title, folder, poster, genres, actors))
    conn.commit()
    conn.close()

def main():
    if not os.path.exists(MOVIE_PATH):
        logging.error(f"Movie path {MOVIE_PATH} not found.")
        return

    existing = get_existing_movies(DATABASE_PATH)
    logging.info(f"Found {len(existing)} movies in database.")

    added = 0
    for folder in os.listdir(MOVIE_PATH):
        folder_path = os.path.join(MOVIE_PATH, folder)
        if not os.path.isdir(folder_path) or folder_path in existing:
            continue

        nfo_file = os.path.join(folder_path, "movie.nfo")
        poster_file = os.path.join(folder_path, "poster.jpg")
        if not os.path.exists(poster_file):
            # Try fallback images
            for alt in ["thumb.jpg", "banner.jpg", "fanart.jpg"]:
                alt_path = os.path.join(folder_path, alt)
                if os.path.exists(alt_path):
                    poster_file = alt_path
                    break

        title, genres, actors = parse_nfo(nfo_file) if os.path.exists(nfo_file) else (folder, "", "")
        insert_movie(DATABASE_PATH, title, folder_path, poster_file if os.path.exists(poster_file) else "", genres, actors)
        added += 1
        logging.info(f"Added: {title}")

    logging.info(f"Rescan complete. {added} new movies added.")

if __name__ == "__main__":
    main()
