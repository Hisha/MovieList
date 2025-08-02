# 🎮 MovieList - FastAPI Movie Library

A FastAPI web app to **browse your movie collection** stored in a mounted folder (e.g., NAS).
Features:

* Dark Bootstrap UI
* Poster grid view with modal details
* Search by title
* Filter by genre and actor
* AJAX pagination (Load More button)
* SQLite database for fast lookups
* Automatic fallback poster

---

## ✅ Requirements

* Python **3.9+**
* FastAPI, Uvicorn, Jinja2, Python-dotenv, and SQLite3
* Access to your movie folder (e.g., `/mnt/Movies`)
  Each movie should be in its own folder with:
* `poster.jpg`
* `movie.nfo` (Kodi-style XML)
* Movie file (e.g., `.mp4`)

Example folder:

```
/mnt/Movies/2 Fast 2 Furious (2003)/
├── 2 Fast 2 Furious (2003).mp4
├── 2 Fast 2 Furious (2003).nfo
└── poster.jpg
```

---

## 📦 Installation

```bash
# 1. Clone repo
git clone https://github.com/your-username/MovieList.git
cd MovieList

# 2. Create virtual environment
python3 -m venv ML_env
source ML_env/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

### **requirements.txt**

```
fastapi
uvicorn
jinja2
python-dotenv
beautifulsoup4
lxml
```

---

## ⚙️ Configuration

Create a `.env` file in the project root:

```
MOVIE_PATH=/mnt/Movies
```

Ensure `/mnt/Movies` is accessible by the app user (or adjust to your NAS mount path).

---

## 🗄 Database Setup

```bash
# Create DB if not exists
sqlite3 movies.db "
CREATE TABLE IF NOT EXISTS movies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    folder TEXT,
    poster TEXT,
    genres TEXT,
    actors TEXT,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_title ON movies(title);
CREATE INDEX IF NOT EXISTS idx_genres ON movies(genres);
CREATE INDEX IF NOT EXISTS idx_actors ON movies(actors);
"
```

---

## 🔍 Scan Movies

Use the provided script to populate the database:

```bash
python3 rescan_movies.py
```

* Adds new movies from `MOVIE_PATH`
* Removes deleted movie entries
* Updates DB with `poster.jpg`, `genres`, and `actors` from `.nfo`

---

## ▶️ Run Locally

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Access:

```
http://<server-ip>:8000/ML
```

---

## 🔄 Run as Systemd Service

Create `/etc/systemd/system/movielist.service`:

```
[Unit]
Description=MovieList FastAPI Movie Library
After=network.target

[Service]
User=youruser
WorkingDirectory=/home/youruser/MovieList
ExecStart=/home/youruser/MovieList/ML_env/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
Environment="PATH=/home/youruser/MovieList/ML_env/bin"

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable movielist
sudo systemctl start movielist
```

Check logs:

```bash
journalctl -u movielist -f
```

---

## 🖼 UI Features

* **Poster grid** (4 per row on desktop, responsive)
* **Modal popup** on click (shows title, genres, actors)
* **AJAX Load More** for smooth pagination
* **Search + Filters** at the top

---

## 🛠 Maintenance

* **Rescan periodically**:

  * Add cron job:

    ```
    0 2 * * * /home/youruser/MovieList/ML_env/bin/python3 /home/youruser/MovieList/rescan_movies.py
    ```
* Update DB indexes if needed for performance.

---

✅ **Everything runs under `/ML` root path**, so it works behind reverse proxies like Nginx.
