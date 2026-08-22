from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from .. import config, db, metrics
from ..date_utils import to_ddmmyyyy
from ..formatting import dashboard_title

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    latest = db.get_latest_entry()
    history = db.get_entries(limit=180)
    app_config = db.get_config()
    settings = db.get_settings()
    payload = metrics.build_dashboard_payload(latest, history, app_config, settings)
    payload["entry_count"] = db.count_entries()
    payload["latest_health_metric"] = db.get_latest_health_metric()
    return request.app.state.templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "data": payload,
            "poll_seconds": config.DASHBOARD_POLL_SECONDS,
            "page_title": dashboard_title(settings.get("display_name")),
        },
    )


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    settings = db.get_settings()
    enabled_categories = settings.get("google_health_enabled_categories") or '["body_composition", "activity", "cardio", "sleep"]'
    date_of_birth_display = None
    if settings.get("date_of_birth"):
        date_of_birth_display = to_ddmmyyyy(settings["date_of_birth"])
    return request.app.state.templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "settings": settings,
            "date_of_birth_display": date_of_birth_display,
            "entry_count": db.count_entries(),
            "enabled_categories": enabled_categories,
            "google_health_message": request.query_params.get("google_health_message"),
        },
    )
