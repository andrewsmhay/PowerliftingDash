"""Pulls the configured Google Sheet tab, maps its header row onto the
generated schema columns, and upserts one SQLite row per dated entry.

Dormant by default: manual entry via the web UI (see routes/entries.py) is
now the primary way data gets into PowerliftingDash. This module only runs
if a `google_sheet_id` is set in Settings (the scheduler skips it entirely
otherwise), for anyone who wants to feed a sheet-based source into the same
`entries` table instead of/alongside typing values into the app.

Column matching: sheet headers are normalised the same way
schema/generate_schema.py normalises Item names, so a header cell of
"Squat 1RM (current)" matches the `squat_1rm_current` column without
requiring the sheet's header text to be typed in snake_case.
"""
import logging
import re
from datetime import datetime, timezone

from . import db
from .date_utils import DateParseError, parse_sheet_date, to_iso
from .numeric import coerce_numeric as _coerce_numeric
from .sheets_client import fetch_tab_values

logger = logging.getLogger("powerliftingdash.sync")


class SyncError(RuntimeError):
    pass


def _normalise_header(header: str) -> str:
    s = header.lower()
    s = s.replace("1rm", "1rm ")
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    s = s.replace("percentage_body_fat", "percent_body_fat")
    return s


def _build_column_index(header_row: list[str], date_column_name: str) -> tuple[int | None, dict[int, str]]:
    """Returns (date_column_index, {column_index: schema_column_name})."""
    known_columns = set(db.entry_columns())
    date_idx = None
    mapped: dict[int, str] = {}

    normalised_date_target = _normalise_header(date_column_name)

    for idx, header in enumerate(header_row):
        if header is None:
            continue
        header_text = str(header).strip()
        if not header_text:
            continue
        if header_text.lower() == date_column_name.lower() or _normalise_header(header_text) == normalised_date_target:
            date_idx = idx
            continue
        normalised = _normalise_header(header_text)
        if normalised in known_columns:
            mapped[idx] = normalised

    return date_idx, mapped



def run_sync() -> dict:
    """Runs one sync pass. Returns a summary dict and records the result in
    app_settings (last_sync_at / last_sync_status / last_sync_message).
    """
    settings = db.get_settings()
    started = datetime.now(timezone.utc)

    try:
        rows = fetch_tab_values(settings)
    except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
        message = f"{type(exc).__name__}: {exc}"
        logger.exception("Sync failed while fetching sheet values")
        db.record_sync_result("error", message)
        raise SyncError(message) from exc

    if not rows:
        db.record_sync_result("error", "Sheet tab returned no rows")
        raise SyncError("Sheet tab returned no rows")

    header_row = rows[0]
    date_column_name = settings.get("date_column_name") or "Date"
    date_idx, column_map = _build_column_index(header_row, date_column_name)

    if date_idx is None:
        message = (
            f"Could not find a '{date_column_name}' column in the header row: {header_row}"
        )
        db.record_sync_result("error", message)
        raise SyncError(message)

    if not column_map:
        message = "No known metric columns matched the header row; check column names against schema/v1_items.csv"
        db.record_sync_result("error", message)
        raise SyncError(message)

    upserted = 0
    skipped = 0
    errors: list[str] = []

    for row_number, row in enumerate(rows[1:], start=2):
        if date_idx >= len(row) or row[date_idx] in (None, ""):
            skipped += 1
            continue
        try:
            entry_date = parse_sheet_date(row[date_idx])
        except DateParseError as exc:
            skipped += 1
            errors.append(f"row {row_number}: {exc}")
            continue

        values = {}
        for col_idx, column_name in column_map.items():
            cell = row[col_idx] if col_idx < len(row) else None
            values[column_name] = _coerce_numeric(cell)

        db.upsert_entry(to_iso(entry_date), row_number, values, source="sheet_sync")
        upserted += 1

    duration = (datetime.now(timezone.utc) - started).total_seconds()
    status = "ok" if not errors else "partial"
    message = f"Synced {upserted} row(s), skipped {skipped}, in {duration:.1f}s"
    if errors:
        message += f". Issues: {'; '.join(errors[:5])}"
        if len(errors) > 5:
            message += f" (+{len(errors) - 5} more)"

    if upserted:
        from . import derive

        derive.recompute_all()

    db.record_sync_result(status, message)
    logger.info(message)
    return {
        "status": status,
        "message": message,
        "upserted": upserted,
        "skipped": skipped,
        "errors": errors,
        "duration_seconds": duration,
    }
