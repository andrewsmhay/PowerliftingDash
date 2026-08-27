"""Parsing for the entry date field, entered manually as dd/mm/yyyy.

dd/mm/yyyy is parsed with an explicit format string, never a locale-guessing
parser, so 03/04 is never silently flipped to April the 3rd.
"""
import re
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

DDMMYYYY_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")

DEFAULT_TIMEZONE = "America/Toronto"


class DateParseError(ValueError):
    pass


def parse_entry_date(raw) -> date:
    """Returns a date object, or raises DateParseError."""
    if raw is None or raw == "":
        raise DateParseError("empty date value")

    text = str(raw).strip()

    match = DDMMYYYY_RE.match(text)
    if match:
        day, month, year = (int(part) for part in match.groups())
        try:
            return date(year, month, day)
        except ValueError as exc:
            raise DateParseError(f"invalid dd/mm/yyyy value: {text!r}") from exc

    # Fall back to an explicit strptime in case the value has a time
    # component too (dd/mm/yyyy HH:MM:SS), still with an explicit format.
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    raise DateParseError(f"unrecognised date format (expected dd/mm/yyyy): {text!r}")


def to_iso(d: date) -> str:
    return d.isoformat()


def to_ddmmyyyy(iso_value: str) -> str:
    d = date.fromisoformat(iso_value)
    return d.strftime("%d/%m/%Y")


def local_today(tz_name: str | None = None) -> date:
    """Returns today's date in the given timezone (falls back to
    DEFAULT_TIMEZONE on a missing or invalid tz string, never UTC, so
    day-boundary calculations like `days_until` match what the lifter sees
    on their own clock).
    """
    try:
        tz = ZoneInfo(tz_name) if tz_name else ZoneInfo(DEFAULT_TIMEZONE)
    except Exception:  # noqa: BLE001 - fall back rather than 500 on a bad tz string
        tz = ZoneInfo(DEFAULT_TIMEZONE)
    return datetime.now(tz).date()


def days_until(event_date_iso: str, today: date | None = None) -> int:
    """Whole days between `today` and the given ISO date (negative if past)."""
    today = today or local_today()
    event = date.fromisoformat(event_date_iso)
    return (event - today).days


def format_time_until(days: int) -> str:
    """Human-readable "time until event" label from a day count."""
    if days > 1:
        return f"In {days} days"
    if days == 1:
        return "Tomorrow"
    if days == 0:
        return "Today"
    if days == -1:
        return "Yesterday"
    return f"{abs(days)} days ago"
