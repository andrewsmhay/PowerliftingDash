import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.sync import _build_column_index, _coerce_numeric, _normalise_header


def test_normalise_header_matches_generated_column_names():
    assert _normalise_header("Squat 1RM (current)") == "squat_1rm_current"
    assert _normalise_header("Percentage Body Fat (to date)") == "percent_body_fat_to_date"
    assert _normalise_header("BMI (target)") == "bmi_target"


def test_build_column_index_finds_date_and_known_columns():
    header = ["Date", "Squat 1RM (current)", "Unrelated column", "BMI"]
    date_idx, mapping = _build_column_index(header, "Date")
    assert date_idx == 0
    assert mapping[1] == "squat_1rm_current"
    assert 2 not in mapping
    assert mapping[3] == "bmi"


def test_coerce_numeric_handles_strings_and_blanks():
    assert _coerce_numeric("123.5") == 123.5
    assert _coerce_numeric("1,234") == 1234.0
    assert _coerce_numeric("") is None
    assert _coerce_numeric(None) is None
    assert _coerce_numeric("not-a-number") is None
    assert _coerce_numeric(42) == 42.0
