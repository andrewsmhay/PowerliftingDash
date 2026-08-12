import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import config, db, scheduler
from .routes import api, entries, pages

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="PowerliftingDash")
app.state.templates = Jinja2Templates(directory=str(config.APP_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(config.APP_DIR / "static")), name="static")

app.include_router(pages.router)
app.include_router(api.router)
app.include_router(entries.router)


@app.on_event("startup")
def on_startup():
    db.init_db()
    scheduler.start()


@app.on_event("shutdown")
def on_shutdown():
    scheduler.stop()


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
