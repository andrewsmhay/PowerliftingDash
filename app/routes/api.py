from fastapi import APIRouter, HTTPException

from .. import auth_provider, db, metrics
from ..sync import SyncError, run_sync

router = APIRouter(prefix="/api")


@router.get("/dashboard")
def dashboard_data():
    latest = db.get_latest_entry()
    history = db.get_entries(limit=180)
    payload = metrics.build_dashboard_payload(latest, history)
    settings = db.get_settings()
    payload["last_sync_at"] = settings.get("last_sync_at")
    payload["last_sync_status"] = settings.get("last_sync_status")
    payload["entry_count"] = db.count_entries()
    return payload


@router.get("/settings")
def get_settings():
    settings = db.get_settings()
    safe = dict(settings)
    safe["service_account_configured"] = bool(settings.get("service_account_json"))
    safe.pop("service_account_json", None)
    safe["service_account_email"] = auth_provider.service_account_email(settings)
    return safe


@router.post("/settings")
def save_settings(payload: dict):
    allowed = {
        "google_sheet_id",
        "entries_tab_name",
        "date_column_name",
        "sync_interval_minutes",
        "timezone",
        "service_account_json",
    }
    fields = {k: v for k, v in payload.items() if k in allowed and v is not None and v != ""}
    if not fields:
        raise HTTPException(status_code=400, detail="No recognised settings fields provided")
    db.update_settings(**fields)
    return {"ok": True}


@router.post("/sync")
def trigger_sync():
    try:
        return run_sync()
    except SyncError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
