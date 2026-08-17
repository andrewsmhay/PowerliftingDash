"""Parsing for the entry date field, entered manually as dd/mm/yyyy.

dd/mm/yyyy is parsed with an explicit format string, never a locale-guessing
parser, so 03/04 is never silently flipped to April the 3rd.
"""
import re
from datetime import date, datetime

DDMMYYYY_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")


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
