"""Manually tracked countdowns to upcoming events (e.g. a meet Andrew plans
to attend, or any other date worth watching a clock tick down to).

Kept separate from the `competitions` table, which is a historical log of
actual meet results - a countdown might never happen, could later be logged
as a real competition once it's over, or might not be a competition at all.
Location is chosen from a small self-maintained picklist
(`countdown_locations`) rather than a bundled global geography dataset, to
keep the app itself lightweight.
"""
from fastapi import APIRouter, HTTPException

from .. import db
from ..date_utils import DateParseError, parse_entry_date, to_ddmmyyyy, to_iso

router = APIRouter()

COUNTDOWN_FIELDS = {"event_name", "country", "region", "city"}


def _validate_location_kind(kind: str) -> None:
    if kind not in db.COUNTDOWN_LOCATION_KINDS:
        raise HTTPException(status_code=400, detail=f"Unknown location kind: {kind!r}")


def _coerce_countdown_values(values: dict) -> dict:
    unknown = set(values) - COUNTDOWN_FIELDS
    if unknown:
        raise HTTPException(
            status_code=400, detail=f"Unknown field(s): {', '.join(sorted(unknown))}"
        )
    event_name = (values.get("event_name") or "").strip()
    if not event_name:
        raise HTTPException(status_code=400, detail="Event name is required.")
    return {
        "event_name": event_name,
        "country": (values.get("country") or "").strip() or None,
        "region": (values.get("region") or "").strip() or None,
        "city": (values.get("city") or "").strip() or None,
    }


def _parse_countdown_date(date_raw) -> str:
    if not date_raw:
        raise HTTPException(status_code=400, detail="Event date is required (dd/mm/yyyy).")
    try:
        return to_iso(parse_entry_date(date_raw))
    except DateParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/countdowns")
def create_countdown(payload: dict):
    event_date_iso = _parse_countdown_date(payload.get("event_date"))
    coerced = _coerce_countdown_values(payload.get("values") or {})

    countdown_id = db.insert_countdown(event_date_iso, coerced)
    saved = db.get_countdown_by_id(countdown_id)
    return {
        "ok": True,
        "id": countdown_id,
        "event_date_ddmmyyyy": to_ddmmyyyy(event_date_iso),
        "countdown": saved,
    }


@router.put("/api/countdowns/{countdown_id}")
def update_countdown(countdown_id: str, payload: dict):
    existing = db.get_countdown_by_id(countdown_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Countdown not found")

    event_date_iso = _parse_countdown_date(payload.get("event_date"))
    coerced = _coerce_countdown_values(payload.get("values") or {})

    db.update_countdown_full(countdown_id, event_date_iso, coerced)
    saved = db.get_countdown_by_id(countdown_id)
    return {
        "ok": True,
        "id": countdown_id,
        "event_date_ddmmyyyy": to_ddmmyyyy(event_date_iso),
        "countdown": saved,
    }


@router.delete("/api/countdowns/{countdown_id}")
def delete_countdown(countdown_id: str):
    deleted = db.delete_countdown(countdown_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Countdown not found")
    return {"ok": True}


@router.post("/api/countdowns/locations")
def add_countdown_location(payload: dict):
    kind = (payload.get("kind") or "").strip()
    value = (payload.get("value") or "").strip()
    _validate_location_kind(kind)
    if not value:
        raise HTTPException(status_code=400, detail="A value is required.")
    result = db.add_countdown_location(kind, value)
    return {"ok": True, "kind": kind, **result}


@router.delete("/api/countdowns/locations/{location_id}")
def delete_countdown_location(location_id: str):
    deleted = db.delete_countdown_location(location_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Location option not found")
    return {"ok": True}
