# 🎬 MovieList 2.0 — Read-Only Kodi Media Catalog

MovieList is a lightweight FastAPI web app for browsing a personal media
collection.  Version 2.0 uses the **existing Kodi MySQL/MariaDB video
library** (`MyVideos131`, Kodi 21 Omega) as the single authoritative
metadata source.  Kodi manages the library; MovieList only displays it.

* Movies and TV shows (series → seasons → episodes)
* Search by title, actor, or genre; genre filters; sorting; pagination
* Recently added movies and recently updated TV shows
* Artwork (posters, fanart, episode thumbs) through a safe local cache
* Dark Bootstrap UI that works on desktop, tablets, and phones
* Health check endpoint; systemd-friendly; no GPU, no Docker

MovieList is **not** a media player and never modifies Kodi data:
no streaming, no playback, no downloads, no metadata editing, no
watch-history management, no library scanning.

---

## Architecture

```
Browser ──> FastAPI (movielist/app.py)
              │  ├─ movielist/kodi.py     read-only queries (SELECT only)
              │  ├─ movielist/db.py       connection pool (READ ONLY sessions)
              │  └─ movielist/artwork.py  safe artwork cache
              ▼
        Kodi MariaDB (MyVideos131)   [SELECT-only account]
              +
        Local artwork cache dir      (POSTers/fanart copied on demand)
```

* All metadata comes from Kodi's views: `movie_view`, `tvshow_view`,
  `season_view`, `episode_view`, and the `art` table.
* Every DB connection runs `SET SESSION TRANSACTION READ ONLY` and uses a
  dedicated SELECT-only MySQL account as defense in depth.
* Artwork is fetched on demand from Kodi's `art` references (local paths
  via configured SMB→mount mappings, or approved HTTPS hosts), cached on
  local disk, and served with cache headers.  Missing/broken artwork
  yields a placeholder; failures are negative-cached.
* No SQLite catalog, no NFO parsing, no filesystem scanning, no
  background services (v2.0 removed the legacy scanner).

Column mappings were verified against Kodi 21 (Omega) source,
`xbmc/video/VideoDatabase.{h,cpp}` (MyVideos131).  Run
`scripts/verify_kodi_schema.py` to confirm them against your database
before first use.

---

## Requirements

* Ubuntu 24.04 (or any Linux with Python 3.10+)
* Python 3.10+ and `python3-venv`
* Network access from the app host to Kodi's MariaDB (TCP 3306)
* Optional: a local mount of the media share for local artwork

---

## Database account setup (manual, one time)

MovieList must **never** run with an administrative MySQL account.
Create a dedicated SELECT-only account on the Kodi host:

```sql
-- See scripts/setup_readonly_user.sql
CREATE USER 'movielist'@'VIDEOAI_HOST'
  IDENTIFIED BY 'CHANGE_ME_STRONG_PASSWORD';
GRANT SELECT ON MyVideos131.* TO 'movielist'@'VIDEOAI_HOST';
FLUSH PRIVILEGES;
```

Replace `VIDEOAI_HOST` with the hostname/IP MovieList connects from.
Verify with `SHOW GRANTS FOR 'movielist'@'VIDEOAI_HOST';` — it must list
only `SELECT`.

If Kodi is upgraded to a new database version (e.g. `MyVideos132`),
grant SELECT on the new database and update `KODI_DB_NAME`.  MovieList
never auto-selects another database version.

---

## Installation

```bash
# 1. Clone and enter the repo
git clone <repo-url> /opt/movielist
cd /opt/movielist

# 2. Create a dedicated system user (once)
sudo useradd --system --home /opt/movielist --shell /usr/sbin/nologin movielist

# 3. Virtual environment
python3 -m venv ML_env
ML_env/bin/pip install -r requirements.txt

# 4. Configuration
cp .env.example .env
sudo install -o movielist -g movielist -m 600 .env   # protect credentials
${EDITOR:-nano} .env                                 # set DB credentials etc.

# 5. Artwork cache directory
sudo mkdir -p /var/lib/movielist/artwork_cache
sudo chown -R movielist:movielist /var/lib/movielist
# ...and point ARTWORK_CACHE_DIR=/var/lib/movielist/artwork_cache in .env

# 6. Smoke-test the database connection (read-only)
sudo -u movielist ML_env/bin/python scripts/verify_kodi_schema.py

# 7. Run manually (optional)
sudo -u movielist ML_env/bin/uvicorn main:app --host 127.0.0.1 --port 8000
```

Open `http://SERVER:8000/ML/` (directly, or through your reverse proxy).

---

## Configuration reference (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `KODI_DB_HOST` | `127.0.0.1` | Kodi MySQL/MariaDB host |
| `KODI_DB_PORT` | `3306` | Port |
| `KODI_DB_NAME` | `MyVideos131` | Database name (explicit; never auto-switched) |
| `KODI_DB_USER` | `movielist` | SELECT-only account |
| `KODI_DB_PASSWORD` | — | Account password |
| `KODI_DB_POOL_SIZE` | `5` | Max pooled connections |
| `MOVIELIST_HOST` / `MOVIELIST_PORT` | `127.0.0.1` / `8000` | Bind address |
| `MOVIELIST_ROOT_PATH` | `/ML` | URL prefix behind the reverse proxy |
| `MOVIELIST_PAGE_SIZE` | `48` | Movies per page |
| `MOVIELIST_SHOWS_PAGE_SIZE` | `36` | Shows per page |
| `MOVIELIST_RECENT_COUNT` | `12` | Items per "recently added" row |
| `ARTWORK_CACHE_DIR` | `./artwork_cache` | Local cache directory |
| `ARTWORK_CACHE_MAX_SIZE` | `2147483648` (2 GiB) | Cache size cap (LRU eviction) |
| `ARTWORK_MAX_BYTES` | `26214400` (25 MiB) | Per-image download cap |
| `ARTWORK_MAX_DIMENSION` | `10000` | Max image width/height |
| `MEDIA_PATH_MAPPINGS` | — | `smb://nas/share/=/mnt/share,...` (or JSON) |
| `APPROVED_ARTWORK_HOSTS` | — | Comma list; empty = remote artwork disabled |
| `ARTWORK_ALLOWED_DIRS` | — | Extra local dirs readable for artwork |
| `LOG_LEVEL` | `INFO` | Python log level |

Notes:

* All artwork URLs/paths from Kodi are treated as untrusted: only mapped
  SMB paths, configured allowed directories, and allowlisted public HTTPS
  hosts are reachable.  Private/loopback/link-local addresses are blocked.
* No media mount is required if all artwork resolves through approved
  remote hosts.
* Never commit `.env`; keep it mode `600`.

---

## systemd deployment

```bash
sudo cp deploy/movielist.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now movielist
sudo systemctl status movielist
journalctl -u movielist -f
```

The service runs unprivileged as `movielist`, bound to `127.0.0.1`,
restarts on failure, and writes logs to journald.

### Health check

```
GET /ML/healthz   -> 200 {"status":"ok"}   or 503 {"status":"degraded"}
```

Use it for load-balancer/monitoring probes.  It reveals no configuration
details.

### Reverse proxy (nginx example)

MovieList is designed to sit behind an existing HTTPS reverse proxy
(it does not terminate TLS itself):

```nginx
location /ML/ {
    proxy_pass http://127.0.0.1:8000/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

The app is configured with `MOVIELIST_ROOT_PATH=/ML`, so all generated
links carry the prefix.  Keep the proxy on localhost or your LAN and
terminate TLS at the proxy.

---

## Upgrades

```bash
sudo systemctl stop movielist
cd /opt/movielist
git pull
ML_env/bin/pip install -r requirements.txt
sudo -u movielist ML_env/bin/python scripts/verify_kodi_schema.py
sudo systemctl start movielist
```

If Kodi was upgraded and created a new database (e.g. `MyVideos132`),
first grant the movielist account SELECT on it, then set
`KODI_DB_NAME=MyVideos132` in `.env`.  MovieList will not switch
automatically.

---

## Testing

Automated tests never touch a real database (the data-access layer is
mocked):

```bash
python3 -m venv ML_env
ML_env/bin/pip install -r requirements-dev.txt
ML_env/bin/python -m pytest
```

Coverage includes: movie/show/season/episode queries, search,
pagination, missing metadata, missing artwork, artwork caching,
unsafe artwork URLs, path traversal, SSRF/allowlist enforcement,
database outages, and static read-only enforcement (no application
module contains write SQL).

### Manual smoke test against the real Kodi database

```bash
# uses only SELECT-level operations; modifies nothing
ML_env/bin/python scripts/verify_kodi_schema.py
```

It verifies grants, READ ONLY session mode, required views/columns, and
executes every application query shape with tiny result sets.

---

## Security model (summary)

* Dedicated SELECT-only DB account + per-connection
  `SET SESSION TRANSACTION READ ONLY` + all SQL parameterized and
  confined to `movielist/kodi.py`.
* Artwork requests are only resolvable by Kodi media id/type; the
  server looks up references itself — users cannot submit URLs.
* Remote artwork: HTTPS/HTTP allowlisted hosts only, DNS results must
  be public addresses, redirects re-validated per hop, size/time/
  dimension caps, image content verified with Pillow.
* Local artwork: configured SMB→mount mappings only, resolved paths
  must stay inside configured roots (no traversal), extension and
  size checks.
* Kodi paths/URLs are never exposed in HTML or JSON responses.
* Database errors return a friendly 503 page without credentials or
  internal details.

---

## License

See [LICENSE](LICENSE).
