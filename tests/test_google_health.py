"""Unit tests for Google Health request and normalisation helpers."""
import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import google_health


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def _civil_date(year, month, day):
    return {"date": {"year": year, "month": month, "day": day}}


def test_refresh_access_token_returns_expiry_and_access_token():
    with patch("httpx.post", return_value=_FakeResponse(200, {"access_token": "fresh", "expires_in": 1200})):
        updates = google_health.refresh_access_token("id", "secret", "refresh")

    assert updates["google_health_access_token"] == "fresh"
    assert updates["google_health_token_expiry"]


def test_body_normalisation_converts_grams_and_millimetres(monkeypatch):
    responses = {
        "weight": [{"weight": {"weightGrams": 82500.0, "sampleTime": {"civilTime": _civil_date(2026, 8, 1)}}}],
        "body-fat": [{"bodyFat": {"percentage": 16.5, "sampleTime": {"civilTime": _civil_date(2026, 8, 1)}}}],
        "height": [{"height": {"heightMillimeters": "1810", "sampleTime": {"civilTime": _civil_date(2026, 8, 2)}}}],
    }
    monkeypatch.setattr(google_health, "fetch_data_points", lambda _token, data_type, _start, _end: responses[data_type])

    result = google_health.fetch_body_composition("token", date(2026, 8, 1), date(2026, 8, 3))

    assert result["entry_fields"]["2026-08-01"] == {"body_weight_mass": 82.5, "percent_body_fat": 16.5}
    assert result["height_cm"] == 181.0


def test_filter_builders_use_documented_category_fields():
    start, end = "2026-08-01", "2026-09-01"
    assert google_health.build_filter("weight", start, end) == (
        'weight.sample_time.civil_time >= "2026-08-01" AND weight.sample_time.civil_time < "2026-09-01"'
    )
    assert google_health.build_filter("steps", start, end) == (
        'steps.interval.civil_start_time >= "2026-08-01" AND steps.interval.civil_start_time < "2026-09-01"'
    )
    assert google_health.build_filter("daily-vo2-max", start, end) == (
        'daily_vo2_max.date >= "2026-08-01" AND daily_vo2_max.date < "2026-09-01"'
    )
    assert google_health.build_filter("sleep", start, end) == (
        'sleep.interval.civil_end_time >= "2026-08-01" AND sleep.interval.civil_end_time < "2026-09-01"'
    )


def test_month_windows_split_at_calendar_boundaries():
    assert list(google_health.iter_month_windows("2026-01-30", "2026-03-02")) == [
        (date(2026, 1, 30), date(2026, 2, 1)),
        (date(2026, 2, 1), date(2026, 3, 1)),
        (date(2026, 3, 1), date(2026, 3, 2)),
    ]
