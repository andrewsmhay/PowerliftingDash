import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import importlib


def make_temp_db(monkeypatch):
    tmpdir = tempfile.mkdtemp()
    from app import config

    monkeypatch.setattr(config, "DATA_DIR", Path(tmpdir))
    monkeypatch.setattr(config, "DB_PATH", Path(tmpdir) / "test.sqlite3")
    from app import db

    importlib.reload(db)
    db.init_db()
    return db


def test_upsert_entry_is_idempotent_on_date(monkeypatch):
    db = make_temp_db(monkeypatch)

    first_id = db.upsert_entry("2026-08-01", 2, {"squat_1rm_current": 150.0})
    second_id = db.upsert_entry("2026-08-01", 3, {"squat_1rm_current": 155.0})

    assert first_id == second_id
    assert db.count_entries() == 1

    latest = db.get_latest_entry()
    assert latest["squat_1rm_current"] == 155.0
    assert latest["source_row_number"] == 3


def test_upsert_entry_creates_new_row_for_new_date(monkeypatch):
    db = make_temp_db(monkeypatch)

    db.upsert_entry("2026-08-01", 2, {"squat_1rm_current": 150.0})
    db.upsert_entry("2026-08-02", 3, {"squat_1rm_current": 152.0})

    assert db.count_entries() == 2
    entries = db.get_entries(limit=10)
    assert [e["entry_date"] for e in entries] == ["2026-08-01", "2026-08-02"]


def test_settings_round_trip(monkeypatch):
    db = make_temp_db(monkeypatch)

    db.update_settings(timezone="Europe/Dublin")
    settings = db.get_settings()

    assert settings["timezone"] == "Europe/Dublin"


def test_upsert_entry_defaults_source_to_manual(monkeypatch):
    db = make_temp_db(monkeypatch)

    db.upsert_entry("2026-08-01", None, {"squat_1rm_current": 150.0})

    latest = db.get_latest_entry()
    assert latest["source"] == "manual"


def test_upsert_entry_records_custom_source(monkeypatch):
    db = make_temp_db(monkeypatch)

    db.upsert_entry(
        "2026-08-01", 2, {"squat_1rm_current": 150.0}, source="bulk_import"
    )

    latest = db.get_latest_entry()
    assert latest["source"] == "bulk_import"


def test_manual_save_overwrites_custom_source_for_same_date(monkeypatch):
    db = make_temp_db(monkeypatch)

    db.upsert_entry(
        "2026-08-01", 2, {"squat_1rm_current": 150.0}, source="bulk_import"
    )
    db.upsert_entry("2026-08-01", None, {"squat_1rm_current": 155.0}, source="manual")

    latest = db.get_latest_entry()
    assert latest["source"] == "manual"
    assert latest["squat_1rm_current"] == 155.0


def test_gap_fill_entry_fields_never_overwrites_existing_values(monkeypatch):
    db = make_temp_db(monkeypatch)
    db.upsert_entry("2026-08-01", None, {"body_weight_mass": 80.0})

    db.gap_fill_entry_fields(
        "2026-08-01",
        {"body_weight_mass": 82.0, "percent_body_fat": 15.0},
        "google_health",
    )
    existing = db.get_entry_by_date("2026-08-01")
    assert existing["body_weight_mass"] == 80.0
    assert existing["percent_body_fat"] == 15.0
    assert existing["body_fat_mass"] == 12.0
    assert existing["source"] == "manual"

    db.gap_fill_entry_fields("2026-08-02", {"body_weight_mass": 82.0}, "google_health")
    inserted = db.get_entry_by_date("2026-08-02")
    assert inserted["body_weight_mass"] == 82.0
    assert inserted["source"] == "google_health"
