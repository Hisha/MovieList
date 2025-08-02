import os
import sqlite3

MOVIES_DIR = "/mnt/Movies"
DB_PATH = "movies.db"

def rescan_movies():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("CREATE TABLE IF NOT EXISTS movies (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, folder TEXT, poster TEXT, genres TEXT, actors TEXT, added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    conn.commit()

    for folder in os.listdir(MOVIES_DIR):
        folder_path = os.path.join(MOVIES_DIR, folder)
        if os.path.isdir(folder_path):
            title = folder
            poster = None
            for file in os.listdir(folder_path):
                if file.lower() == "poster.jpg" or file.lower() == "poster.png":
                    poster = f"{folder}/{file}"
            cur.execute("SELECT id FROM movies WHERE folder=?", (folder,))
            if not cur.fetchone():
                cur.execute("INSERT INTO movies (title, folder, poster) VALUES (?, ?, ?)", (title, folder, poster))
                print(f"Added: {title}")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    rescan_movies()
