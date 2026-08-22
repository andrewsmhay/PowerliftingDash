"""Routes for the explicit Google Health connect and synchronise workflow."""
import json
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from .. import config, db, derive, google_health

router = APIRouter()
DEFAULT_CATEGORIES = ["body_composition", "activity", "cardio", "sleep"]


def _redirect_uri() -> str:
    return f"{config.PUBLIC_BASE_URL}/google-health/oauth/callback"


def _enabled_categories(settings: dict) -> list[str]:
    value = settings.get("google_health_enabled_categories")
    if not value:
        return DEFAULT_CATEGORIES
    try:
        selected = json.loads(value)
    except (TypeError, ValueError):
        return DEFAULT_CATEGORIES
    if not isinstance(selected, list):
        return DEFAULT_CATEGORIES
    allowed = set(DEFAULT_CATEGORIES)
    return [category for category in selected if category in allowed]


def _sync_window(settings: dict) -> tuple[date, date]:
    today = datetime.now(timezone.utc).date()
    last_sync = settings.get("google_health_last_sync_at")
    if last_sync:
        try:
            return date.fromisoformat(last_sync[:10]), today + timedelta(days=1)
        except (TypeError, ValueError):
            pass
    try:
        history_days = int(settings.get("google_health_history_days") or 730)
    except (TypeError, ValueError):
        history_days = 730
    return today - timedelta(days=max(history_days, 1)), today + timedelta(days=1)


def synchronise_google_health() -> dict:
    """Runs one inline incremental sync, recording a useful failure for Settings.

    It is shared by the manual endpoint and the dashboard cadence check. No
    background process calls this function.
    """
    settings = db.get_settings()
    if not settings.get("google_health_refresh_token"):
        raise google_health.FetchError("Google Health is not connected. Connect it from Settings first.")
    start_date, end_date = _sync_window(settings)
    try:
        token, token_updates = google_health.get_valid_access_token(settings)
        if token_updates:
            db.update_settings(**token_updates)
        results = []
        for category in _enabled_categories(settings):
            fetcher = {
                "body_composition": google_health.fetch_body_composition,
                "activity": google_health.fetch_activity,
                "cardio": google_health.fetch_cardio,
                "sleep": google_health.fetch_sleep,
            }[category]
            results.append(fetcher(token, start_date, end_date))

        metrics_by_date: dict[str, dict] = {}
        entry_fields_by_date: dict[str, dict] = {}
        height_cm = None
        for result in results:
            for entry_date, values in result["metrics"].items():
                metrics_by_date.setdefault(entry_date, {}).update(values)
            for entry_date, values in result["entry_fields"].items():
                entry_fields_by_date.setdefault(entry_date, {}).update(values)
            if result.get("height_cm") is not None:
                height_cm = result["height_cm"]

        for entry_date, values in metrics_by_date.items():
            db.upsert_health_metric(entry_date, values)
        for entry_date, values in entry_fields_by_date.items():
            db.gap_fill_entry_fields(entry_date, values, "google_health")
        if entry_fields_by_date:
            derive.recompute_all()

        now = datetime.now(timezone.utc).isoformat()
        updates = {
            "google_health_last_sync_at": now,
            "google_health_last_sync_error": None,
        }
        if height_cm is not None:
            updates["google_health_height_cm"] = height_cm
        db.update_settings(**updates)
        return {
            "ok": True,
            "metrics_dates": len(metrics_by_date),
            "entry_dates": len(entry_fields_by_date),
            "synced_at": now,
        }
    except google_health.FetchError as exc:
        db.update_settings(
            google_health_last_sync_error=str(exc),
        )
        raise


@router.get("/google-health/connect")
def connect_google_health():
    settings = db.get_settings()
    client_id = settings.get("google_health_client_id")
    client_secret = settings.get("google_health_client_secret")
    if not client_id or not client_secret:
        query = urlencode({"google_health_message": "Save a Google Health client ID and secret first."})
        return RedirectResponse(f"/settings?{query}", status_code=303)
    return RedirectResponse(
        google_health.build_authorize_url(client_id, _redirect_uri()), status_code=302
    )


@router.get("/google-health/oauth/callback")
def google_health_callback(code: str | None = None, error: str | None = None):
    if error:
        query = urlencode({"google_health_message": f"Google Health connection was cancelled: {error}"})
        return RedirectResponse(f"/settings?{query}", status_code=303)
    if not code:
        query = urlencode({"google_health_message": "Google did not return an authorisation code."})
        return RedirectResponse(f"/settings?{query}", status_code=303)
    settings = db.get_settings()
    try:
        token_fields = google_health.exchange_authorization_code(
            settings.get("google_health_client_id") or "",
            settings.get("google_health_client_secret") or "",
            code,
            _redirect_uri(),
        )
    except google_health.FetchError as exc:
        message = f"Google Health could not be connected: {exc}"
    else:
        db.update_settings(
            **token_fields,
            google_health_connected_at=datetime.now(timezone.utc).isoformat(),
            google_health_last_sync_error=None,
        )
        try:
            synchronise_google_health()
            message = "Google Health connected and historical data synchronised."
        except google_health.FetchError as exc:
            message = f"Google Health was connected, but the first sync failed: {exc}"
    query = urlencode({"google_health_message": message})
    return RedirectResponse(f"/settings?{query}", status_code=303)


@router.post("/api/google-health/sync")
def sync_google_health():
    try:
        return synchronise_google_health()
    except google_health.FetchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/api/google-health/disconnect")
def disconnect_google_health():
    db.update_settings(
        google_health_access_token=None,
        google_health_refresh_token=None,
        google_health_token_expiry=None,
        google_health_connected_at=None,
        google_health_last_sync_at=None,
        google_health_last_sync_error=None,
        google_health_height_cm=None,
    )
    return {"ok": True}
