"""Targets & competition config - a hardcoded goals screen, not a daily
entry form.

These are the values Andrew sets once and rarely touches again (his 1RM
targets, his competition lift numbers, his body composition/BMI/BMR
goals) - unlike the daily readings on /entries/new, they don't get a new
value with every dated entry. They live as scalar columns on the single
`app_settings` row (see `db.get_config`/`db.update_config`), generated
from the same schema_manifest.json as everything else so this route never
hard-codes field names.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from starlette.requests import Request

from .. import db, derive
from ..numeric import coerce_numeric

router = APIRouter()


def _config_fields_by_area() -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for col in db.config_columns():
        grouped.setdefault(col["area"], []).append(col)
    return grouped


@router.get("/targets", response_class=HTMLResponse)
def targets_page(request: Request):
    config = db.get_config()
    return request.app.state.templates.TemplateResponse(
        "targets.html",
        {
            "request": request,
            "areas": _config_fields_by_area(),
            "config": config,
        },
    )


@router.post("/api/targets")
def save_targets(payload: dict):
    values = payload.get("values") or {}

    known_columns = {c["column"] for c in db.config_columns()}
    unknown = set(values) - known_columns
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown target/competition field(s): {', '.join(sorted(unknown))}",
        )

    numeric_values = {col: coerce_numeric(raw) for col, raw in values.items()}
    db.update_config(**numeric_values)

    # A changed target or competition value invalidates every stored
    # remaining/delta figure across history, not just the latest entry.
    derive.recompute_all()

    return {"ok": True, "config": db.get_config()}
