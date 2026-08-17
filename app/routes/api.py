from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from .. import db, metrics
from ..date_utils import DateParseError, parse_entry_date, to_iso
from ..openpowerlifting import FetchError, fetch_personal_bests

router = APIRouter(prefix="/api")


@router.get("/dashboard")
def dashboard_data():
    latest = db.get_latest_entry()
    history = db.get_entries(limit=180)
    config = db.get_config()
    settings = db.get_settings()
    payload = metrics.build_dashboard_payload(latest, history, config, settings)
    payload["entry_count"] = db.count_entries()
    return payload


@router.get("/settings")
def get_settings():
    return db.get_settings()


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
    allowed = {"timezone", "display_name", "date_of_birth", "openpowerlifting_username"}
    clearable = {"display_name", "date_of_birth", "openpowerlifting_username"}

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
