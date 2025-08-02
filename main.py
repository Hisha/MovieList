from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from utils import init_db, get_movies, get_all_genres, get_all_actors
import uvicorn

app = FastAPI(root_path="/ML")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

init_db()


@app.get("/", response_class=HTMLResponse)
def home(request: Request, search: str = None, genre: str = None, actor: str = None):
    movies = get_movies(search=search, genre=genre, actor=actor)
    genres = get_all_genres()
    actors = get_all_actors()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "movies": movies,
        "genres": genres,
        "actors": actors
    })


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
