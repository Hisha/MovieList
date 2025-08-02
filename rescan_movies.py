#!/usr/bin/env python3
import logging
from utils import init_db, scan_movies, add_movie_to_db

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")

if __name__ == "__main__":
    logging.info("Rescanning movies...")
    init_db()
    movies = scan_movies()
    for movie in movies:
        add_movie_to_db(movie)
    logging.info(f"✅ Rescan complete. {len(movies)} folders checked.")
