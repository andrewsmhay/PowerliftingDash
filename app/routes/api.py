import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from .. import config, db, metrics
from ..date_utils import DateParseError, parse_entry_date, to_iso
from ..openpowerlifting import FetchError, fetch_personal_bests
from . import google_health as google_health_routes

router = APIRouter(prefix="/api")


@router.get("/dashboard")
def dashboard_data():
    settings = db.get_settings()
    last_sync = settings.get("google_health_last_sync_at")
    connected = bool(settings.get("google_health_refresh_token"))
    should_sync = connected
    if last_sync:
        try:
            last_sync_at = datetime.fromisoformat(last_sync.replace("Z", "+00:00"))
            if last_sync_at.tzinfo is None:
                last_sync_at = last_sync_at.replace(tzinfo=timezone.utc)
            should_sync = (datetime.now(timezone.utc) - last_sync_at).total_seconds() > config.GOOGLE_HEALTH_SYNC_INTERVAL_SECONDS
        except (TypeError, ValueError):
            should_sync = True
    if should_sync:
        try:
            google_health_routes.synchronise_google_health()
        except google_health_routes.google_health.FetchError:
            # The dashboard remains usable if a request-triggered Health refresh fails.
            pass
    latest = db.get_latest_entry()
    history = db.get_entries(limit=180)
    app_config = db.get_config()
    settings = db.get_settings()
    payload = metrics.build_dashboard_payload(latest, history, app_config, settings)
    payload["entry_count"] = db.count_entries()
    payload["latest_health_metric"] = db.get_latest_health_metric()
    return payload


@router.get("/settings")
def get_settings():
    settings = db.get_settings()
    settings.pop("google_health_client_secret", None)
    settings.pop("google_health_access_token", None)
    settings.pop("google_health_refresh_token", None)
    settings["google_health_client_secret_set"] = bool(db.get_settings().get("google_health_client_secret"))
    return settings


def _refresh_opl_bests(username: str) -> dict:
    """Fetches personal bests for `username` and stores the result (or the
    error) on app_settings. Returns the bests dict on success.
    """
    fetched_at = datetime.now(timezone.utc).isoformat()
    try:
        bests = fetch_personal_bests(username)
    except FetchError as exc:
        db.update_settings(opl_fetch_error=str(exc), opl_fetched_at=fetched_at)
        raise
    db.update_settings(
        opl_best_squat=bests["squat"],
        opl_best_bench=bests["bench"],
        opl_best_deadlift=bests["deadlift"],
        opl_best_total=bests["total"],
        opl_fetched_at=fetched_at,
        opl_fetch_error=None,
    )
    return bests


@router.post("/settings")
def save_settings(payload: dict):
    allowed = {
        "timezone", "display_name", "date_of_birth", "openpowerlifting_username",
        "google_health_client_id", "google_health_client_secret",
        "google_health_enabled_categories",
    }
    clearable = {
        "display_name", "date_of_birth", "openpowerlifting_username",
        "google_health_client_id", "google_health_client_secret",
        "google_health_enabled_categories",
    }

    fields = {}
    for key, value in payload.items():
        if key not in allowed:
            continue
        if value is None or value == "":
            if key in clearable:
                fields[key] = None
            continue
        fields[key] = value

    if "date_of_birth" in fields and fields["date_of_birth"] is not None:
        try:
            fields["date_of_birth"] = to_iso(parse_entry_date(fields["date_of_birth"]))
        except DateParseError as exc:
            raise HTTPException(status_code=400, detail=f"Date of birth: {exc}") from exc

    if "google_health_enabled_categories" in fields and fields["google_health_enabled_categories"] is not None:
        try:
            categories = json.loads(fields["google_health_enabled_categories"])
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Google Health categories must be a JSON list.") from exc
        valid_categories = {"body_composition", "activity", "cardio", "sleep"}
        if not isinstance(categories, list) or any(category not in valid_categories for category in categories):
            raise HTTPException(status_code=400, detail="Google Health categories are invalid.")
        fields["google_health_enabled_categories"] = json.dumps(categories)

    if not fields:
        raise HTTPException(status_code=400, detail="No recognised settings fields provided")

    previous_username = (db.get_settings().get("openpowerlifting_username") or "").strip()
    db.update_settings(**fields)

    opl_error = None
    if "openpowerlifting_username" in fields:
        new_username = (fields["openpowerlifting_username"] or "").strip()
        if new_username and new_username != previous_username:
            try:
                _refresh_opl_bests(new_username)
            except FetchError as exc:
                opl_error = str(exc)

    response = {"ok": True}
    if opl_error:
        response["openpowerlifting_warning"] = opl_error
    return response


@router.post("/openpowerlifting/refresh")
def refresh_openpowerlifting():
    username = (db.get_settings().get("openpowerlifting_username") or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="No OpenPowerlifting username configured.")
    try:
        bests = _refresh_opl_bests(username)
    except FetchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "bests": bests}
