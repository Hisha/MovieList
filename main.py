"""MovieList 2.0 entrypoint.

Run with:  uvicorn main:app --host 0.0.0.0 --port 8000
"""

import logging

from movielist.app import create_app
from movielist.config import Settings

settings = Settings.load()
logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = create_app(settings)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.movielist_host,
        port=settings.movielist_port,
    )
