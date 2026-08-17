import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import date

import pytest

from app.date_utils import DateParseError, parse_entry_date, to_ddmmyyyy, to_iso


def test_parses_ddmmyyyy_string():
    assert parse_entry_date("03/04/2026") == date(2026, 4, 3)


def test_parses_single_digit_ddmmyyyy():
    assert parse_entry_date("3/4/2026") == date(2026, 4, 3)


def test_never_flips_to_mmddyyyy():
    # 25 can't be a month, so a mm/dd parser would fail here; a correct
    # dd/mm parser reads day=25, month=1.
    assert parse_entry_date("25/01/2026") == date(2026, 1, 25)


def test_rejects_empty():
    with pytest.raises(DateParseError):
        parse_entry_date("")


def test_rejects_garbage():
    with pytest.raises(DateParseError):
        parse_entry_date("not-a-date")


def test_rejects_invalid_calendar_date():
    with pytest.raises(DateParseError):
        parse_entry_date("31/02/2026")


def test_round_trip_iso_and_ddmmyyyy():
    d = date(2026, 8, 12)
    assert to_iso(d) == "2026-08-12"
    assert to_ddmmyyyy(to_iso(d)) == "12/08/2026"
