"""Covers the upgrade path for a pre-existing (v1-shape) database that still
has target/competition values sitting on `entries` rows, predating the
/targets config split. `init_db()` must add the new `app_settings` columns
and backfill them from the legacy entries data without clobbering anything a
user has already set on /targets.
"""
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import importlib


def _make_legacy_db(monkeypatch):
    """Builds a DB in the OLD shape: entries carries target/competition
    columns directly, and app_settings has none of the 12 new config
    columns. Mirrors what a real pre-split SQLite file looks like.
    """
    tmpdir = tempfile.mkdtemp()
    from app import config

    monkeypatch.setattr(config, "DATA_DIR", Path(tmpdir))
    monkeypatch.setattr(config, "DB_PATH", Path(tmpdir) / "legacy.sqlite3")

    from app import db

    importlib.reload(db)

    with db.connection() as conn:
        conn.executescript(
            """
            CREATE TABLE entries (
                id TEXT PRIMARY KEY,
                entry_date TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL DEFAULT 'manual',
                source_row_number INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                squat_1rm_current REAL,
                squat_1rm_target REAL,
                squat_1rm_competition REAL,
                bench_1rm_current REAL,
                bench_1rm_target REAL,
                bench_1rm_competition REAL,
                body_weight_mass REAL,
                body_weight_mass_target REAL
            );
            CREATE TABLE app_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                google_sheet_id TEXT,
                entries_tab_name TEXT NOT NULL DEFAULT '',
                date_column_name TEXT NOT NULL DEFAULT 'Date',
                sync_interval_minutes INTEGER NOT NULL DEFAULT 10,
                timezone TEXT NOT NULL DEFAULT 'America/Toronto',
                service_account_json TEXT,
                last_sync_at TEXT,
                last_sync_status TEXT,
                last_sync_message TEXT,
                updated_at TEXT
            );
            INSERT INTO app_settings (id, updated_at) VALUES (1, '2026-01-01T00:00:00+00:00');
            """
        )
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO entries (
                id, entry_date, source, source_row_number, created_at, updated_at,
                squat_1rm_current, squat_1rm_target, squat_1rm_competition,
                bench_1rm_current, bench_1rm_target, bench_1rm_competition,
                body_weight_mass, body_weight_mass_target
            ) VALUES (?, ?, 'manual', NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()), "2026-06-01", now, now,
                140.0, 170.0, 150.0,
                90.0, 110.0, 95.0,
                85.0, 80.0,
            ),
        )

    return db


def test_init_db_migrates_legacy_target_columns_into_app_settings(monkeypatch):
    db = _make_legacy_db(monkeypatch)

    # Upgrade: this is exactly what happens on next app startup against an
    # existing v1-shape database file.
    db.init_db()

    config_values = db.get_config()

    assert config_values["squat_1rm_target"] == 170.0
    assert config_values["squat_1rm_competition"] == 150.0
    assert config_values["bench_1rm_target"] == 110.0
    assert config_values["bench_1rm_competition"] == 95.0
    assert config_values["body_weight_mass_target"] == 80.0

    # The legacy entries row itself is untouched - migration only adds/
    # populates app_settings columns, it does not rewrite entries.
    with db.connection() as conn:
        entries_cols = {
            row["name"] for row in conn.execute("PRAGMA table_info(entries)").fetchall()
        }
    assert "squat_1rm_target" in entries_cols  # legacy column left in place


def test_init_db_backfill_does_not_overwrite_existing_config(monkeypatch):
    db = _make_legacy_db(monkeypatch)

    # Simulate a user who already configured /targets with a different
    # number than whatever is sitting on the legacy entries row.
    db._ensure_config_columns()
    with db.connection() as conn:
        conn.execute("UPDATE app_settings SET squat_1rm_target = 999.0 WHERE id = 1")

    db.init_db()

    config_values = db.get_config()
    assert config_values["squat_1rm_target"] == 999.0  # not clobbered by legacy 170.0
