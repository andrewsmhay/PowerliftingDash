"""Competition history log.

A distinct timeline of actual meet results (federation, meet name, placing,
lifts and total), kept separate from the day-to-day `entries` table so a
training PR and a competition result are never conflated. Unlike the
manual entry form, meets do not feed the derived-column pipeline in
derive.py - they are a standalone record shown on their own page, with
DOTS/Wilks-2/IPF GL scores calculated on the fly for display using each
meet's own bodyweight (not the athlete's current bodyweight).
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from starlette.requests import Request

from .. import db
from ..analytics import compute_dots_score, compute_ipf_gl_score, compute_wilks2_score
from ..date_utils import DateParseError, days_until, format_time_until, local_today, parse_entry_date, to_ddmmyyyy, to_iso
from ..numeric import coerce_numeric
from ..openpowerlifting import FetchError, fetch_competition_history

router = APIRouter()

TEXT_FIELDS = {"meet_name", "federation", "location", "weight_class", "placing", "notes"}
NUMERIC_FIELDS = {"bodyweight_kg", "squat_kg", "bench_kg", "deadlift_kg", "total_kg"}
ALL_FIELDS = TEXT_FIELDS | NUMERIC_FIELDS


def _validate_fields(values: dict) -> None:
    unknown = set(values) - ALL_FIELDS
    if unknown:
        raise HTTPException(
            status_code=400, detail=f"Unknown field(s): {', '.join(sorted(unknown))}"
        )


def _coerced_values(values: dict) -> dict:
    coerced = {}
    for field in TEXT_FIELDS:
        if field in values:
            text = (values.get(field) or "").strip()
            coerced[field] = text or None
    for field in NUMERIC_FIELDS:
        if field in values:
            coerced[field] = coerce_numeric(values.get(field))
    return coerced


def _scores_for(meet: dict, sex: str | None) -> dict:
    total = meet.get("total_kg")
    bodyweight = meet.get("bodyweight_kg")
    return {
        "dots": compute_dots_score(total, bodyweight, sex),
        "wilks2": compute_wilks2_score(total, bodyweight, sex),
        "ipf_gl": compute_ipf_gl_score(total, bodyweight, sex),
    }


def _countdown_display(countdown: dict, today) -> dict:
    countdown["display_date"] = to_ddmmyyyy(countdown["event_date"])
    days = days_until(countdown["event_date"], today)
    countdown["days_until"] = days
    countdown["time_until"] = format_time_until(days)
    countdown["display_location"] = ", ".join(
        part for part in (countdown.get("city"), countdown.get("region"), countdown.get("country")) if part
    ) or None
    return countdown


@router.get("/competitions", response_class=HTMLResponse)
def competitions_list_page(request: Request):
    settings = db.get_settings()
    sex = settings.get("lifter_sex")
    meets = db.get_all_competitions_desc()
    for meet in meets:
        meet["display_date"] = to_ddmmyyyy(meet["competition_date"])
        meet["scores"] = _scores_for(meet, sex)

    today = local_today(settings.get("timezone"))
    upcoming, past = [], []
    for countdown in db.get_all_countdowns():
        _countdown_display(countdown, today)
        (upcoming if countdown["days_until"] >= 0 else past).append(countdown)
    past.reverse()  # get_all_countdowns() is ascending; most-recently-past first reads better

    return request.app.state.templates.TemplateResponse(
        "competitions_list.html",
        {
            "request": request,
            "meets": meets,
            "sex_configured": sex in ("male", "female"),
            "countdowns_upcoming": upcoming,
            "countdowns_past": past,
            "countdown_locations": db.get_all_countdown_locations(),
        },
    )


@router.get("/competitions/new", response_class=HTMLResponse)
def new_competition_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        "competition_form.html",
        {
            "request": request,
            "meet": {},
            "editing": False,
            "competition_id": None,
        },
    )


@router.get("/competitions/{competition_id}/edit", response_class=HTMLResponse)
def edit_competition_page(request: Request, competition_id: str):
    meet = db.get_competition_by_id(competition_id)
    if not meet:
        raise HTTPException(status_code=404, detail="Competition not found")
    meet = dict(meet)
    meet["competition_date"] = to_ddmmyyyy(meet["competition_date"])
    return request.app.state.templates.TemplateResponse(
        "competition_form.html",
        {
            "request": request,
            "meet": meet,
            "editing": True,
            "competition_id": competition_id,
        },
    )


@router.post("/api/competitions")
def create_competition(payload: dict):
    date_raw = payload.get("competition_date")
    values = payload.get("values") or {}

    if not date_raw:
        raise HTTPException(status_code=400, detail="competition_date is required (dd/mm/yyyy)")
    try:
        meet_date = parse_entry_date(date_raw)
    except DateParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _validate_fields(values)
    coerced = _coerced_values(values)
    if not any(value is not None for value in coerced.values()):
        raise HTTPException(
            status_code=400,
            detail="Provide at least one detail (meet name, lifts, or bodyweight) to save a competition.",
        )

    competition_id = db.insert_competition(to_iso(meet_date), coerced)
    saved = db.get_competition_by_id(competition_id)
    return {
        "ok": True,
        "id": competition_id,
        "competition_date_ddmmyyyy": to_ddmmyyyy(to_iso(meet_date)),
        "competition": saved,
    }


@router.put("/api/competitions/{competition_id}")
def update_competition(competition_id: str, payload: dict):
    existing = db.get_competition_by_id(competition_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Competition not found")

    date_raw = payload.get("competition_date")
    values = payload.get("values") or {}

    if not date_raw:
        raise HTTPException(status_code=400, detail="competition_date is required (dd/mm/yyyy)")
    try:
        meet_date = parse_entry_date(date_raw)
    except DateParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _validate_fields(values)
    coerced = {field: _coerced_values(values).get(field) for field in ALL_FIELDS}

    db.update_competition_full(competition_id, to_iso(meet_date), coerced)
    saved = db.get_competition_by_id(competition_id)
    return {
        "ok": True,
        "id": competition_id,
        "competition_date_ddmmyyyy": to_ddmmyyyy(to_iso(meet_date)),
        "competition": saved,
    }


@router.delete("/api/competitions/{competition_id}")
def delete_competition(competition_id: str):
    deleted = db.delete_competition(competition_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Competition not found")
    return {"ok": True}


def _sync_dedup_key(date_iso: str, meet_name, total_kg) -> tuple:
    return (date_iso, (meet_name or "").strip().lower(), total_kg)


@router.post("/api/competitions/sync-openpowerlifting")
def sync_openpowerlifting_competitions():
    """Imports meets from the OpenPowerlifting username configured in
    Settings. Only meets not already logged here are added - matched on
    date, meet name and total so a manually entered meet, or a meet with
    edited notes, is never duplicated or overwritten. Existing rows are
    never touched by this route.
    """
    username = (db.get_settings().get("openpowerlifting_username") or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="No OpenPowerlifting username configured.")

    try:
        fetched = fetch_competition_history(username)
    except FetchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    existing = db.get_all_competitions_desc()
    seen = {
        _sync_dedup_key(row["competition_date"], row.get("meet_name"), row.get("total_kg"))
        for row in existing
    }

    imported_meets = []
    skipped = 0
    for meet in fetched:
        key = _sync_dedup_key(meet["competition_date_iso"], meet.get("meet_name"), meet.get("total_kg"))
        if key in seen:
            skipped += 1
            continue
        db.insert_competition(meet["competition_date_iso"], meet)
        seen.add(key)
        imported_meets.append(meet.get("meet_name") or meet["competition_date_iso"])

    return {
        "ok": True,
        "imported": len(imported_meets),
        "skipped": skipped,
        "imported_meets": imported_meets,
    }
