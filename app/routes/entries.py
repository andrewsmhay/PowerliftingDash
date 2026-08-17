"""Manual data entry - the primary way values get into PowerliftingDash.

A form grouped by Area (Goals / Status), generated from the
`configured_in_settings=True` columns in schema_manifest.json that also
live on the `entries` table (storage="entries") - i.e. the daily readings
that genuinely change with each dated entry. Target and competition values
(storage="app_settings") are hardcoded once on the /targets screen instead
and are deliberately excluded here, so adding or removing a daily manual
metric only ever means editing schema/v1_items.csv and re-running
schema/generate_schema.py - this route never hard-codes field names.

A new entry only needs to contain the Goals (lift) fields, the Status
(body composition) fields, or both - a section left blank is simply not
recorded for that date rather than rejected, so the form does not force a
gym day and a weigh-in day to be the same day. Editing and deleting past
entries, and wiping the whole table, live here too (see /entries,
/entries/{id}/edit and /api/entries/delete-all).
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from starlette.requests import Request

from .. import db, derive
from ..date_utils import DateParseError, parse_entry_date, to_ddmmyyyy, to_iso
from ..numeric import coerce_numeric

router = APIRouter()


def _manual_columns() -> set[str]:
    """Manual, per-date columns (Goals + Status). Excludes target/competition
    config, which lives on /targets instead.
    """
    return {
        c["column"]
        for c in db.load_manifest()
        if c["configured_in_settings"] and c.get("storage", "entries") == "entries"
    }


def _manual_fields_by_area() -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for col in db.load_manifest():
        if not col["configured_in_settings"] or col.get("storage", "entries") != "entries":
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


def _validate_manual_values(values: dict) -> set[str]:
    """Shared checks for both create and edit: no target/competition fields,
    no unrecognised fields. Returns the set of submitted column names.
    """
    manual_columns = _manual_columns()
    config_columns = {c["column"] for c in db.config_columns()}
    submitted = set(values)

    misplaced_config = submitted & config_columns
    if misplaced_config:
        raise HTTPException(
            status_code=400,
            detail=(
                "Target/competition field(s) "
                f"({', '.join(sorted(misplaced_config))}) are configured once on the "
                "/targets screen, not entered per date. Update them there instead."
            ),
        )

    unknown = submitted - manual_columns
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown or non-manual field(s): {', '.join(sorted(unknown))}",
        )

    return submitted


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
            "editing": False,
            "entry_id": None,
        },
    )


@router.get("/entries", response_class=HTMLResponse)
def entries_list_page(request: Request):
    columns = [
        c
        for c in db.load_manifest()
        if c["configured_in_settings"] and c.get("storage", "entries") == "entries"
    ]
    entries = db.get_all_entries_desc()
    for entry in entries:
        entry["display_date"] = to_ddmmyyyy(entry["entry_date"])
    return request.app.state.templates.TemplateResponse(
        "entries_list.html",
        {
            "request": request,
            "columns": columns,
            "entries": entries,
        },
    )


@router.get("/entries/{entry_id}/edit", response_class=HTMLResponse)
def edit_entry_page(request: Request, entry_id: str):
    entry = db.get_entry_by_id(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    return request.app.state.templates.TemplateResponse(
        "entry_form.html",
        {
            "request": request,
            "areas": _manual_fields_by_area(),
            "latest": entry,
            "today": to_ddmmyyyy(entry["entry_date"]),
            "entry_count": db.count_entries(),
            "editing": True,
            "entry_id": entry_id,
        },
    )


@router.post("/api/entries")
def save_entry(payload: dict):
    entry_date_raw = payload.get("entry_date")
    values = payload.get("values") or {}

    if not entry_date_raw:
        raise HTTPException(status_code=400, detail="entry_date is required (dd/mm/yyyy)")

    try:
        entry_date = parse_entry_date(entry_date_raw)
    except DateParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _validate_manual_values(values)

    numeric_values = {col: coerce_numeric(raw) for col, raw in values.items()}
    if not any(v is not None for v in numeric_values.values()):
        raise HTTPException(
            status_code=400,
            detail=(
                "Provide at least one Lifts or Body Composition value to save an entry - "
                "fill in one section, the other, or both."
            ),
        )

    entry_id = db.upsert_entry(to_iso(entry_date), None, numeric_values, source="manual")
    derive.recompute_all()

    saved = db.get_entry_by_date(to_iso(entry_date))
    return {"ok": True, "id": entry_id, "entry_date_ddmmyyyy": to_ddmmyyyy(to_iso(entry_date)), "entry": saved}


@router.put("/api/entries/{entry_id}")
def update_entry(entry_id: str, payload: dict):
    existing = db.get_entry_by_id(entry_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Entry not found")

    entry_date_raw = payload.get("entry_date")
    values = payload.get("values") or {}

    if not entry_date_raw:
        raise HTTPException(status_code=400, detail="entry_date is required (dd/mm/yyyy)")

    try:
        entry_date = parse_entry_date(entry_date_raw)
    except DateParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _validate_manual_values(values)

    entry_date_iso = to_iso(entry_date)
    conflict = db.get_entry_by_date(entry_date_iso)
    if conflict and conflict["id"] != entry_id:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Another entry already exists for {to_ddmmyyyy(entry_date_iso)}. "
                "Edit that entry instead, or change the date."
            ),
        )

    manual_columns = sorted(_manual_columns())
    numeric_values = {col: coerce_numeric(values.get(col)) for col in manual_columns}
    if not any(v is not None for v in numeric_values.values()):
        raise HTTPException(
            status_code=400,
            detail=(
                "An entry needs at least one Lifts or Body Composition value - "
                "delete the entry instead if you want to remove it entirely."
            ),
        )

    db.update_entry_full(entry_id, entry_date_iso, numeric_values, manual_columns)
    derive.recompute_all()

    saved = db.get_entry_by_id(entry_id)
    return {"ok": True, "id": entry_id, "entry_date_ddmmyyyy": to_ddmmyyyy(entry_date_iso), "entry": saved}


@router.delete("/api/entries/{entry_id}")
def delete_single_entry(entry_id: str):
    deleted = db.delete_entry(entry_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Entry not found")
    derive.recompute_all()
    return {"ok": True}


@router.post("/api/entries/delete-all")
def delete_all_entries(payload: dict):
    if not payload.get("confirm"):
        raise HTTPException(
            status_code=400,
            detail="Confirmation required: pass {\"confirm\": true} to delete every entry.",
        )
    removed = db.delete_all_entries()
    return {"ok": True, "removed": removed}
