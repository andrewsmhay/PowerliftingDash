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


def test_insert_competition_stores_all_fields_and_returns_new_id(monkeypatch):
    db = make_temp_db(monkeypatch)

    competition_id = db.insert_competition(
        "2026-06-15",
        {
            "meet_name": "Ontario Provincials",
            "federation": "CPU",
            "location": "Ottawa, ON",
            "weight_class": "93kg",
            "placing": "1st",
            "bodyweight_kg": 92.4,
            "squat_kg": 220.0,
            "bench_kg": 150.0,
            "deadlift_kg": 250.0,
            "total_kg": 620.0,
            "notes": "Best meet so far",
        },
    )

    assert db.count_competitions() == 1
    saved = db.get_competition_by_id(competition_id)
    assert saved["meet_name"] == "Ontario Provincials"
    assert saved["competition_date"] == "2026-06-15"
    assert saved["total_kg"] == 620.0
    assert saved["placing"] == "1st"


def test_insert_competition_leaves_unspecified_fields_null(monkeypatch):
    db = make_temp_db(monkeypatch)

    competition_id = db.insert_competition("2026-06-15", {"meet_name": "Club Meet"})
    saved = db.get_competition_by_id(competition_id)

    assert saved["meet_name"] == "Club Meet"
    assert saved["federation"] is None
    assert saved["total_kg"] is None


def test_update_competition_full_overwrites_and_clears_fields(monkeypatch):
    db = make_temp_db(monkeypatch)

    competition_id = db.insert_competition(
        "2026-06-15",
        {"meet_name": "Club Meet", "federation": "CPU", "total_kg": 500.0},
    )

    db.update_competition_full(
        competition_id,
        "2026-06-16",
        {"meet_name": "Club Meet (corrected)", "total_kg": 510.0},
    )

    updated = db.get_competition_by_id(competition_id)
    assert updated["competition_date"] == "2026-06-16"
    assert updated["meet_name"] == "Club Meet (corrected)"
    assert updated["total_kg"] == 510.0
    # federation was omitted from the update payload, so it is cleared, not preserved.
    assert updated["federation"] is None


def test_get_all_competitions_desc_orders_newest_first(monkeypatch):
    db = make_temp_db(monkeypatch)

    db.insert_competition("2026-01-01", {"meet_name": "First"})
    db.insert_competition("2026-06-01", {"meet_name": "Third"})
    db.insert_competition("2026-03-01", {"meet_name": "Second"})

    meets = db.get_all_competitions_desc()
    assert [meet["meet_name"] for meet in meets] == ["Third", "Second", "First"]


def test_get_competition_by_id_returns_none_for_unknown_id(monkeypatch):
    db = make_temp_db(monkeypatch)
    assert db.get_competition_by_id("does-not-exist") is None


def test_delete_competition_removes_row_and_reports_success(monkeypatch):
    db = make_temp_db(monkeypatch)
    competition_id = db.insert_competition("2026-06-15", {"meet_name": "Club Meet"})

    assert db.delete_competition(competition_id) is True
    assert db.count_competitions() == 0
    assert db.get_competition_by_id(competition_id) is None


def test_delete_competition_returns_false_for_unknown_id(monkeypatch):
    db = make_temp_db(monkeypatch)
    assert db.delete_competition("does-not-exist") is False
