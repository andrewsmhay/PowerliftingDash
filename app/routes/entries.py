"""Manual data entry - the primary way values get into PowerliftingDash.

A form grouped by Area (Goals / Status), generated from the
`configured_in_settings=True` columns in schema_manifest.json, so adding or
removing a manual metric only ever means editing schema/v1_items.csv and
re-running schema/generate_schema.py - this route never hard-codes field
names.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from starlette.requests import Request

from .. import db, derive
from ..date_utils import DateParseError, parse_sheet_date, to_ddmmyyyy, to_iso
from ..numeric import coerce_numeric

router = APIRouter()


def _manual_fields_by_area() -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for col in db.load_manifest():
        if not col["configured_in_settings"]:
            continue
        grouped.setdefault(col["area"], []).append(col)
    return grouped


def _today_ddmmyyyy() -> str:
    settings = db.get_settings()
    tz_name = settings.get("timezone") or "America/Toronto"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:  # noqa: BLE001 - fall back rather than 500 on a bad tz string
        tz = ZoneInfo("America/Toronto")
    return datetime.now(tz).strftime("%d/%m/%Y")


@router.get("/entries/new", response_class=HTMLResponse)
def new_entry_page(request: Request):
    latest = db.get_latest_entry() or {}
    return request.app.state.templates.TemplateResponse(
        "entry_form.html",
        {
            "request": request,
            "areas": _manual_fields_by_area(),
            "latest": latest,
            "today": _today_ddmmyyyy(),
            "entry_count": db.count_entries(),
        },
    )


@router.post("/api/entries")
def save_entry(payload: dict):
    entry_date_raw = payload.get("entry_date")
    values = payload.get("values") or {}

    if not entry_date_raw:
        raise HTTPException(status_code=400, detail="entry_date is required (dd/mm/yyyy)")

    try:
        entry_date = parse_sheet_date(entry_date_raw)
    except DateParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    manual_columns = {c["column"] for c in db.load_manifest() if c["configured_in_settings"]}
    unknown = set(values) - manual_columns
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown or non-manual field(s): {', '.join(sorted(unknown))}",
        )

    numeric_values = {col: coerce_numeric(raw) for col, raw in values.items()}

    entry_id = db.upsert_entry(to_iso(entry_date), None, numeric_values, source="manual")
    derive.recompute_all()

    saved = db.get_entry_by_date(to_iso(entry_date))
    return {"ok": True, "id": entry_id, "entry_date_ddmmyyyy": to_ddmmyyyy(to_iso(entry_date)), "entry": saved}
