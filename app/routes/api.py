from fastapi import APIRouter, HTTPException

from .. import db, metrics

router = APIRouter(prefix="/api")


@router.get("/dashboard")
def dashboard_data():
    latest = db.get_latest_entry()
    history = db.get_entries(limit=180)
    config = db.get_config()
    payload = metrics.build_dashboard_payload(latest, history, config)
    payload["entry_count"] = db.count_entries()
    return payload


@router.get("/settings")
def get_settings():
    return db.get_settings()


@router.post("/settings")
def save_settings(payload: dict):
    allowed = {"timezone"}
    fields = {k: v for k, v in payload.items() if k in allowed and v is not None and v != ""}
    if not fields:
        raise HTTPException(status_code=400, detail="No recognised settings fields provided")
    db.update_settings(**fields)
    return {"ok": True}
