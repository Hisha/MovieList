import os
import sqlite3
import re
from bs4 import BeautifulSoup

def init_db(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS movies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        folder TEXT,
        genres TEXT,
        actors TEXT,
        description TEXT,
        added_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()
    conn.close()

def parse_nfo(nfo_path):
    genres, actors, plot = [], [], ""
    if os.path.exists(nfo_path):
        with open(nfo_path, "r", encoding="utf-8", errors="ignore") as f:
            soup = BeautifulSoup(f.read(), "xml")
            genres = [g.text for g in soup.find_all("genre")]
            actors = [a.text for a in soup.find_all("actor")]
            plot_tag = soup.find("plot")
            plot = plot_tag.text if plot_tag else ""
    return genres, actors, plot

def scan_movies(movie_path, db_path):
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM movies")  # Clear old data

    for folder in sorted(os.listdir(movie_path)):
        folder_path = os.path.join(movie_path, folder)
        if not os.path.isdir(folder_path):
            continue
        title = re.sub(r"\s*\(\d{4}\)", "", folder)  # Remove year from title
        nfo_file = os.path.join(folder_path, "movie.nfo")
        genres, actors, description = parse_nfo(nfo_file)
        cur.execute("INSERT INTO movies (title, folder, genres, actors, description) VALUES (?, ?, ?, ?, ?)",
                    (title, folder, ",".join(genres), ",".join(actors), description))
    conn.commit()
    conn.close()

def get_movies(db_path, genre=None, actor=None, search=None):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    query = "SELECT title, folder, genres, actors, description FROM movies WHERE 1=1"
    params = []
    if genre:
        query += " AND genres LIKE ?"
        params.append(f"%{genre}%")
    if actor:
        query += " AND actors LIKE ?"
        params.append(f"%{actor}%")
    if search:
        query += " AND title LIKE ?"
        params.append(f"%{search}%")
    query += " ORDER BY added_on DESC"
    cur.execute(query, params)
    movies = cur.fetchall()
    conn.close()
    return movies

def get_filters(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT genres FROM movies")
    all_genres = set()
    for row in cur.fetchall():
        all_genres.update(row[0].split(","))
    cur.execute("SELECT DISTINCT actors FROM movies")
    all_actors = set()
    for row in cur.fetchall():
        all_actors.update(row[0].split(","))
    conn.close()
    return sorted(filter(None, all_genres)), sorted(filter(None, all_actors))
