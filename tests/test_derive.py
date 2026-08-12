import sys
import tempfile
import importlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def make_temp_db(monkeypatch):
    tmpdir = tempfile.mkdtemp()
    from app import config

    monkeypatch.setattr(config, "DATA_DIR", Path(tmpdir))
    monkeypatch.setattr(config, "DB_PATH", Path(tmpdir) / "test.sqlite3")
    from app import db

    importlib.reload(db)
    db.init_db()
    return db


def test_compute_row_derived_remaining_and_competition_delta():
    from app.derive import compute_row_derived

    row = {
        "squat_1rm_current": 161.0,
        "bench_1rm_current": 100.0,
        "deadlift_1rm_current": 200.0,
        "body_weight_mass": 88.0,
    }
    config = {
        "squat_1rm_target": 170.0,
        "squat_1rm_competition": 150.0,
        "bench_1rm_target": 110.0,
        "bench_1rm_competition": 95.0,
        "deadlift_1rm_target": 210.0,
        "deadlift_1rm_competition": 190.0,
    }
    derived = compute_row_derived(row, baselines={"body_weight_mass": 90.0}, config=config)

    assert derived["squat_1rm_remaining"] == 9.0
    assert derived["squat_1rm_competition_delta"] == 11.0
    assert derived["total_weight_lifted_current"] == 461.0
    assert derived["total_weight_lifted_target"] == 490.0
    assert derived["total_weight_lifted_in_competition"] == 435.0
    assert derived["total_weight_lifted_remaining"] == 29.0
    # weight_change_since_comp uses the "to date" baseline convention (documented assumption)
    assert derived["weight_change_since_comp"] == -2.0


def test_compute_row_derived_missing_values_yield_none_not_errors():
    from app.derive import compute_row_derived

    row = {"squat_1rm_current": 161.0}  # target/competition missing from config
    derived = compute_row_derived(row, baselines={}, config={})

    assert derived["squat_1rm_remaining"] is None
    assert derived["squat_1rm_competition_delta"] is None
    assert derived["total_weight_lifted_current"] is None


def test_status_remaining_and_to_date_are_signed():
    from app.derive import compute_row_derived

    row = {
        "body_weight_mass": 87.0,
        "bmi": 26.5,
    }
    config = {
        "body_weight_mass_target": 84.0,
        "bmi_target": 24.0,
    }
    derived = compute_row_derived(
        row, baselines={"body_weight_mass": 90.0, "bmi": 28.0}, config=config
    )

    assert derived["body_weight_mass_remaining"] == -3.0  # target - current
    assert derived["body_weight_mass_to_date"] == -3.0  # current - baseline
    assert derived["bmi_remaining"] == -2.5
    assert derived["bmi_to_date"] == -1.5


def test_recompute_all_uses_earliest_entry_as_baseline(monkeypatch):
    db = make_temp_db(monkeypatch)
    from app import derive

    db.upsert_entry("2026-08-01", None, {"body_weight_mass": 90.0}, source="manual")
    db.upsert_entry("2026-08-05", None, {"body_weight_mass": 88.0}, source="manual")
    db.upsert_entry("2026-08-10", None, {"body_weight_mass": 85.0}, source="manual")

    updated = derive.recompute_all()
    assert updated == 3

    entries = db.get_entries(limit=10)
    to_dates = {e["entry_date"]: e["body_weight_mass_to_date"] for e in entries}
    assert to_dates["2026-08-01"] == 0.0
    assert to_dates["2026-08-05"] == -2.0
    assert to_dates["2026-08-10"] == -5.0


def test_recompute_all_rebaselines_when_an_earlier_entry_is_backfilled(monkeypatch):
    db = make_temp_db(monkeypatch)
    from app import derive

    db.upsert_entry("2026-08-05", None, {"body_weight_mass": 88.0}, source="manual")
    derive.recompute_all()
    assert db.get_entry_by_date("2026-08-05")["body_weight_mass_to_date"] == 0.0

    # Backfill an earlier date - the baseline should move and 08-05's to_date
    # should update accordingly rather than staying stale.
    db.upsert_entry("2026-08-01", None, {"body_weight_mass": 91.0}, source="manual")
    derive.recompute_all()

    assert db.get_entry_by_date("2026-08-01")["body_weight_mass_to_date"] == 0.0
    assert db.get_entry_by_date("2026-08-05")["body_weight_mass_to_date"] == -3.0


def test_recompute_all_on_empty_db_is_a_noop(monkeypatch):
    make_temp_db(monkeypatch)
    from app import derive

    assert derive.recompute_all() == 0


def test_recompute_all_sources_target_and_competition_from_config(monkeypatch):
    """Targets/competition are hardcoded on /targets (app_settings), not on
    entries - recompute_all() must read the current config snapshot and
    apply it uniformly, including to rows saved before the config existed.
    """
    db = make_temp_db(monkeypatch)
    from app import derive

    db.upsert_entry("2026-08-01", None, {"squat_1rm_current": 150.0}, source="manual")
    derive.recompute_all()
    assert db.get_entry_by_date("2026-08-01")["squat_1rm_remaining"] is None

    db.update_config(squat_1rm_target=170.0, squat_1rm_competition=140.0)
    derive.recompute_all()

    entry = db.get_entry_by_date("2026-08-01")
    assert entry["squat_1rm_remaining"] == 20.0
    assert entry["squat_1rm_competition_delta"] == 10.0

    # Changing the target again re-applies to the same historical row.
    db.update_config(squat_1rm_target=160.0)
    derive.recompute_all()
    assert db.get_entry_by_date("2026-08-01")["squat_1rm_remaining"] == 10.0
