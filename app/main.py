import logging

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import config, db
from .routes import api, competitions, countdowns, entries, google_health, pages, targets

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Powerlifting Dashboard")
app.state.templates = Jinja2Templates(directory=str(config.APP_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(config.APP_DIR / "static")), name="static")

app.include_router(pages.router)
app.include_router(api.router)
app.include_router(google_health.router)
app.include_router(entries.router)
app.include_router(targets.router)
app.include_router(competitions.router)
app.include_router(countdowns.router)


@app.on_event("startup")
def on_startup():
    db.init_db()


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    # Browsers probe this path directly regardless of the <link rel="icon">
    # tag; serve the same SVG mark so it doesn't 404 in the console.
    return FileResponse(config.APP_DIR / "static" / "favicon.svg", media_type="image/svg+xml")
