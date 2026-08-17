from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from .. import config, db, metrics

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    latest = db.get_latest_entry()
    history = db.get_entries(limit=180)
    app_config = db.get_config()
    payload = metrics.build_dashboard_payload(latest, history, app_config)
    payload["entry_count"] = db.count_entries()
    return request.app.state.templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "data": payload,
            "poll_seconds": config.DASHBOARD_POLL_SECONDS,
        },
    )


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    settings = db.get_settings()
    return request.app.state.templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "settings": settings,
            "entry_count": db.count_entries(),
        },
    )
