"""SQLite access layer. One connection per request via FastAPI dependency;
WAL mode so concurrent web requests don't block each other.
"""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config


def _dict_factory(cursor, row):
    fields = [col[0] for col in cursor.description]
    return dict(zip(fields, row))


def get_connection() -> sqlite3.Connection:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=30)
    conn.row_factory = _dict_factory
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


@contextmanager
def connection():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Creates tables from schema.sql if they don't already exist, then runs
    the small idempotent migrations below for databases created by an older
    version of this app.

    `CREATE TABLE IF NOT EXISTS` is a no-op on a table that already exists,
    so introducing new `app_settings` columns (the target/competition config
    fields) would otherwise silently fail to appear on an existing database
    and the first write to them would crash. `_ensure_config_columns` adds
    any missing ones with `ALTER TABLE ... ADD COLUMN`, and
    `_backfill_config_from_latest_entry` seeds them from whatever
    target/competition values were last saved on an entry row, so upgrading
    does not silently blank out Andrew's existing goals.
    """
    sql = config.SCHEMA_SQL_PATH.read_text()
    with connection() as conn:
        conn.executescript(sql)
    _ensure_config_columns()
    _ensure_settings_columns()
    _ensure_health_metrics_table()
    _ensure_competitions_table()
    _backfill_config_from_latest_entry()


def load_manifest() -> list[dict]:
    return json.loads(config.SCHEMA_MANIFEST_PATH.read_text())["columns"]


def entry_columns() -> list[str]:
    """Columns on the `entries` table: daily manual readings plus every
    derived column. Excludes target/competition config, which lives on
    `app_settings` instead (see `config_columns`).
    """
    return [c["column"] for c in load_manifest() if c.get("storage", "entries") == "entries"]


def config_columns() -> list[dict]:
    """Manifest entries for the hardcoded target/competition fields that
    live on `app_settings`, edited from the /targets screen.
    """
    return [c for c in load_manifest() if c.get("storage") == "app_settings"]


def _ensure_config_columns() -> None:
    """Adds any target/competition columns missing from an existing
    `app_settings` table (idempotent - safe to run on every startup).
    """
    with connection() as conn:
        existing = {
            row["name"] for row in conn.execute("PRAGMA table_info(app_settings)").fetchall()
        }
        for col in config_columns():
            if col["column"] not in existing:
                conn.execute(f"ALTER TABLE app_settings ADD COLUMN {col['column']} {col['sql_type']}")


def _ensure_settings_columns() -> None:
    """Adds the personal-profile and OpenPowerlifting-cache columns missing
    from an existing `app_settings` table (idempotent - safe to run on every
    startup). These are hardcoded app metadata, not manifest-driven, same as
    `timezone` itself.
    """
    settings_columns = [
        ("display_name", "TEXT"),
        ("date_of_birth", "TEXT"),
        ("height_cm", "REAL"),
        ("openpowerlifting_username", "TEXT"),
        ("opl_best_squat", "REAL"),
        ("opl_best_bench", "REAL"),
        ("opl_best_deadlift", "REAL"),
        ("opl_best_total", "REAL"),
        ("opl_fetched_at", "TEXT"),
        ("opl_fetch_error", "TEXT"),
        ("google_health_client_id", "TEXT"),
        ("google_health_client_secret", "TEXT"),
        ("google_health_access_token", "TEXT"),
        ("google_health_refresh_token", "TEXT"),
        ("google_health_token_expiry", "TEXT"),
        ("google_health_connected_at", "TEXT"),
        ("google_health_last_sync_at", "TEXT"),
        ("google_health_last_sync_error", "TEXT"),
        ("google_health_history_days", "INTEGER DEFAULT 730"),
        ("google_health_height_cm", "REAL"),
        ("google_health_enabled_categories", "TEXT"),
        ("dashboard_layout", "TEXT"),
        ("dashboard_rotation_seconds", "INTEGER DEFAULT 30"),
        ("lifter_sex", "TEXT"),
    ]
    with connection() as conn:
        existing = {
            row["name"] for row in conn.execute("PRAGMA table_info(app_settings)").fetchall()
        }
        for column, sql_type in settings_columns:
            if column not in existing:
                conn.execute(f"ALTER TABLE app_settings ADD COLUMN {column} {sql_type}")


def _ensure_health_metrics_table() -> None:
    """Creates the separate daily health table without routing activity and
    recovery measurements through the goals and status manifest.
    """
    with connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS health_metrics (
                entry_date TEXT PRIMARY KEY,
                steps INTEGER,
                distance_km REAL,
                floors_climbed REAL,
                active_minutes REAL,
                active_zone_minutes REAL,
                calories_burned REAL,
                resting_heart_rate REAL,
                heart_rate_variability_ms REAL,
                vo2_max REAL,
                sleep_minutes REAL,
                respiratory_rate REAL,
                oxygen_saturation_pct REAL,
                source TEXT NOT NULL DEFAULT 'google_health',
                synced_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_health_metrics_date ON health_metrics(entry_date);
            """
        )


def _ensure_competitions_table() -> None:
    """Creates the meet history log: a distinct table from `entries`, since a
    competition result (federation, placing, meet total) is a one-off event
    rather than a dated training reading. Uses its own UUID id (not
    competition_date) as the primary key so, unlike `entries`, more than one
    row could in principle share a date without conflict.
    """
    with connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS competitions (
                id TEXT PRIMARY KEY,
                competition_date TEXT NOT NULL,
                meet_name TEXT,
                federation TEXT,
                location TEXT,
                weight_class TEXT,
                placing TEXT,
                bodyweight_kg REAL,
                squat_kg REAL,
                bench_kg REAL,
                deadlift_kg REAL,
                total_kg REAL,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_competitions_date ON competitions(competition_date);
            """
        )


def _backfill_config_from_latest_entry() -> None:
    """One-time seed: if a target/competition config column is still NULL
    but the most recent entry row has a (legacy) value under the same
    column name, copy it across. Only runs while the columns themselves are
    genuinely unset, so it never overwrites a value Andrew has already
    configured on /targets.
    """
    cols = [c["column"] for c in config_columns()]
    if not cols:
        return
    with connection() as conn:
        settings_row = conn.execute("SELECT * FROM app_settings WHERE id = 1").fetchone() or {}
        if all(settings_row.get(c) is not None for c in cols):
            return  # already fully configured, nothing to backfill

        table_cols = {
            row["name"] for row in conn.execute("PRAGMA table_info(entries)").fetchall()
        }
        legacy_cols = [c for c in cols if c in table_cols]
        if not legacy_cols:
            return

        latest = conn.execute(
            f"SELECT {', '.join(legacy_cols)} FROM entries ORDER BY entry_date DESC LIMIT 1"
        ).fetchone()
        if not latest:
            return

        to_backfill = {
            c: latest[c]
            for c in legacy_cols
            if settings_row.get(c) is None and latest.get(c) is not None
        }
        if not to_backfill:
            return

        set_clause = ", ".join(f"{c} = ?" for c in to_backfill)
        conn.execute(f"UPDATE app_settings SET {set_clause} WHERE id = 1", list(to_backfill.values()))


def get_config() -> dict:
    """Current target/competition values, as configured on /targets."""
    cols = [c["column"] for c in config_columns()]
    with connection() as conn:
        row = conn.execute(f"SELECT {', '.join(cols)} FROM app_settings WHERE id = 1").fetchone()
        return row or {}


def update_config(**fields) -> None:
    """Saves target/competition values. Silently ignores any key that is not
    a known config column, so callers cannot accidentally write into an
    unrelated app_settings field via this path.
    """
    valid = {c["column"] for c in config_columns()}
    fields = {k: v for k, v in fields.items() if k in valid}
    update_settings(**fields)


def get_settings() -> dict:
    with connection() as conn:
        row = conn.execute("SELECT * FROM app_settings WHERE id = 1").fetchone()
        return row or {}


def update_settings(**fields) -> None:
    if not fields:
        return
    fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    columns = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values())
    with connection() as conn:
        conn.execute(f"UPDATE app_settings SET {columns} WHERE id = 1", values)


def get_latest_entry() -> dict | None:
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM entries ORDER BY entry_date DESC LIMIT 1"
        ).fetchone()
        return row


def get_entries(limit: int = 180) -> list[dict]:
    """Most recent `limit` entries, oldest first (good for chart x-axes)."""
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM entries ORDER BY entry_date DESC LIMIT ?", (limit,)
        ).fetchall()
    return list(reversed(rows))


def get_health_metrics(limit: int = 180) -> list[dict]:
    """Most recent health metric rows, oldest first for chart x-axis order."""
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM health_metrics ORDER BY entry_date DESC LIMIT ?", (limit,)
        ).fetchall()
    return list(reversed(rows))


def count_entries() -> int:
    with connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM entries").fetchone()
        return row["n"] if row else 0


def upsert_entry(
    entry_date_iso: str,
    source_row_number: int | None,
    values: dict,
    source: str = "manual",
) -> str:
    """Insert a new entry for entry_date_iso, or update it in place if a row
    for that date already exists (idempotent). Returns the row's UUID.

    `values` may be a partial dict (e.g. only the manually-entered columns);
    columns not present are left untouched on update, or NULL on insert.
    """
    import uuid

    now = datetime.now(timezone.utc).isoformat()
    columns = entry_columns()
    provided = {c: values[c] for c in columns if c in values}

    with connection() as conn:
        existing = conn.execute(
            "SELECT id FROM entries WHERE entry_date = ?", (entry_date_iso,)
        ).fetchone()

        if existing:
            entry_id = existing["id"]
            if provided:
                set_clause = ", ".join(f"{c} = ?" for c in provided)
                conn.execute(
                    f"UPDATE entries SET {set_clause}, source = ?, source_row_number = ?, "
                    "updated_at = ? WHERE id = ?",
                    [*provided.values(), source, source_row_number, now, entry_id],
                )
            else:
                conn.execute(
                    "UPDATE entries SET source = ?, source_row_number = ?, updated_at = ? "
                    "WHERE id = ?",
                    [source, source_row_number, now, entry_id],
                )
        else:
            entry_id = str(uuid.uuid4())
            safe_values = {c: values.get(c) for c in columns}
            col_list = ", ".join(columns)
            placeholders = ", ".join("?" for _ in columns)
            conn.execute(
                f"INSERT INTO entries "
                f"(id, entry_date, source, source_row_number, created_at, updated_at, {col_list}) "
                f"VALUES (?, ?, ?, ?, ?, ?, {placeholders})",
                [
                    entry_id,
                    entry_date_iso,
                    source,
                    source_row_number,
                    now,
                    now,
                    *safe_values.values(),
                ],
            )
        return entry_id


def gap_fill_entry_fields(entry_date_iso: str, values: dict, source_label: str) -> str:
    """Adds Health values only where a dated entry currently has no value.

    A manual reading remains authoritative. Existing rows also keep their
    source and timestamp, because filling an empty field is not a manual edit.
    """
    import uuid

    allowed = {"body_weight_mass", "percent_body_fat", "body_fat_mass"}
    supplied = {key: value for key, value in values.items() if key in allowed and value is not None}
    now = datetime.now(timezone.utc).isoformat()
    with connection() as conn:
        existing = conn.execute(
            "SELECT * FROM entries WHERE entry_date = ?", (entry_date_iso,)
        ).fetchone()
        if not existing:
            entry_id = str(uuid.uuid4())
            safe_values = {column: None for column in entry_columns()}
            safe_values.update(supplied)
            weight = safe_values.get("body_weight_mass")
            percentage = safe_values.get("percent_body_fat")
            if safe_values.get("body_fat_mass") is None and weight is not None and percentage is not None:
                safe_values["body_fat_mass"] = weight * percentage / 100
            columns = entry_columns()
            conn.execute(
                f"INSERT INTO entries (id, entry_date, source, source_row_number, created_at, updated_at, "
                f"{', '.join(columns)}) VALUES (?, ?, ?, NULL, ?, ?, {', '.join('?' for _ in columns)})",
                [entry_id, entry_date_iso, source_label, now, now, *[safe_values[column] for column in columns]],
            )
            return entry_id

        entry_id = existing["id"]
        to_fill = {key: value for key, value in supplied.items() if existing.get(key) is None}
        final_weight = to_fill.get("body_weight_mass", existing.get("body_weight_mass"))
        final_percentage = to_fill.get("percent_body_fat", existing.get("percent_body_fat"))
        if (
            existing.get("body_fat_mass") is None
            and final_weight is not None
            and final_percentage is not None
        ):
            to_fill.setdefault("body_fat_mass", final_weight * final_percentage / 100)
        if to_fill:
            set_clause = ", ".join(f"{column} = ?" for column in to_fill)
            conn.execute(
                f"UPDATE entries SET {set_clause} WHERE id = ?",
                [*to_fill.values(), entry_id],
            )
        return entry_id


def upsert_health_metric(entry_date_iso: str, values: dict) -> None:
    """Stores a partial Google Health daily summary, replacing only metrics
    returned by the requested categories while retaining other categories.
    """
    valid = {
        "steps", "distance_km", "floors_climbed", "active_minutes",
        "active_zone_minutes", "calories_burned", "resting_heart_rate",
        "heart_rate_variability_ms", "vo2_max", "sleep_minutes",
        "respiratory_rate", "oxygen_saturation_pct",
    }
    supplied = {key: value for key, value in values.items() if key in valid and value is not None}
    if not supplied:
        return
    synced_at = datetime.now(timezone.utc).isoformat()
    with connection() as conn:
        existing = conn.execute(
            "SELECT entry_date FROM health_metrics WHERE entry_date = ?", (entry_date_iso,)
        ).fetchone()
        if existing:
            set_clause = ", ".join(f"{column} = ?" for column in supplied)
            conn.execute(
                f"UPDATE health_metrics SET {set_clause}, source = 'google_health', synced_at = ? "
                "WHERE entry_date = ?",
                [*supplied.values(), synced_at, entry_date_iso],
            )
        else:
            columns = list(supplied)
            conn.execute(
                f"INSERT INTO health_metrics (entry_date, {', '.join(columns)}, source, synced_at) "
                f"VALUES (?, {', '.join('?' for _ in columns)}, 'google_health', ?)",
                [entry_date_iso, *supplied.values(), synced_at],
            )


def get_latest_health_metric() -> dict | None:
    with connection() as conn:
        return conn.execute(
            "SELECT * FROM health_metrics ORDER BY entry_date DESC LIMIT 1"
        ).fetchone()


def update_computed_columns(entry_id: str, values: dict) -> None:
    """Writes a dict of computed columns onto an existing entry, without
    touching updated_at/source (this is a derived-value refresh, not a new
    save of manually entered data).
    """
    if not values:
        return
    columns = list(values.keys())
    set_clause = ", ".join(f"{c} = ?" for c in columns)
    with connection() as conn:
        conn.execute(
            f"UPDATE entries SET {set_clause} WHERE id = ?",
            [*values.values(), entry_id],
        )


def get_all_entries_asc() -> list[dict]:
    """Every entry, oldest first - used to recompute baselines for the
    'to date' family of derived columns.
    """
    with connection() as conn:
        rows = conn.execute("SELECT * FROM entries ORDER BY entry_date ASC").fetchall()
    return rows


def get_entry_by_date(entry_date_iso: str) -> dict | None:
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM entries WHERE entry_date = ?", (entry_date_iso,)
        ).fetchone()
        return row


def get_entry_by_id(entry_id: str) -> dict | None:
    with connection() as conn:
        row = conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
        return row


def get_all_entries_desc() -> list[dict]:
    """Every entry, newest first - used by the /entries management list."""
    with connection() as conn:
        rows = conn.execute("SELECT * FROM entries ORDER BY entry_date DESC").fetchall()
    return rows


def update_entry_full(
    entry_id: str,
    entry_date_iso: str,
    manual_values: dict,
    manual_columns: list[str],
    source: str = "manual",
) -> None:
    """Edit-mode update for a specific entry (by id, not by date).

    Unlike `upsert_entry` (used by the daily quick-add form, where a column
    absent from the payload is left untouched so a "weight only" or "goals
    only" save doesn't blank out the other section), this treats
    `manual_values` as the full, authoritative state of every manual column:
    anything not present is written as NULL, so clearing a field on the edit
    screen and saving actually clears it. Also allows moving the entry to a
    different `entry_date` - callers must check for a date collision with
    another row first (see routes/entries.py).
    """
    now = datetime.now(timezone.utc).isoformat()
    safe_values = {c: manual_values.get(c) for c in manual_columns}
    set_clause = ", ".join(f"{c} = ?" for c in safe_values)
    with connection() as conn:
        conn.execute(
            f"UPDATE entries SET entry_date = ?, {set_clause}, source = ?, updated_at = ? "
            "WHERE id = ?",
            [entry_date_iso, *safe_values.values(), source, now, entry_id],
        )


def delete_entry(entry_id: str) -> bool:
    """Deletes a single entry by id. Returns True if a row was removed."""
    with connection() as conn:
        cur = conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
        return cur.rowcount > 0


def delete_all_entries() -> int:
    """Wipes every row from `entries` (leaves `app_settings` - targets and
    competition numbers - untouched). Returns the number of rows removed.
    """
    with connection() as conn:
        cur = conn.execute("DELETE FROM entries")
        return cur.rowcount


COMPETITION_COLUMNS = [
    "meet_name", "federation", "location", "weight_class", "placing",
    "bodyweight_kg", "squat_kg", "bench_kg", "deadlift_kg", "total_kg", "notes",
]


def insert_competition(competition_date_iso: str, values: dict) -> str:
    """Inserts a new meet result row. Returns the row's UUID."""
    import uuid

    now = datetime.now(timezone.utc).isoformat()
    competition_id = str(uuid.uuid4())
    safe_values = {c: values.get(c) for c in COMPETITION_COLUMNS}
    col_list = ", ".join(COMPETITION_COLUMNS)
    placeholders = ", ".join("?" for _ in COMPETITION_COLUMNS)
    with connection() as conn:
        conn.execute(
            f"INSERT INTO competitions "
            f"(id, competition_date, created_at, updated_at, {col_list}) "
            f"VALUES (?, ?, ?, ?, {placeholders})",
            [competition_id, competition_date_iso, now, now, *safe_values.values()],
        )
    return competition_id


def update_competition_full(competition_id: str, competition_date_iso: str, values: dict) -> None:
    """Edit-mode update for a specific meet (by id). Treats `values` as the
    full, authoritative state of every field: anything not present is
    written as NULL, so clearing a field on the edit screen and saving
    actually clears it. Also allows moving the meet to a different date.
    """
    now = datetime.now(timezone.utc).isoformat()
    safe_values = {c: values.get(c) for c in COMPETITION_COLUMNS}
    set_clause = ", ".join(f"{c} = ?" for c in safe_values)
    with connection() as conn:
        conn.execute(
            f"UPDATE competitions SET competition_date = ?, {set_clause}, updated_at = ? "
            "WHERE id = ?",
            [competition_date_iso, *safe_values.values(), now, competition_id],
        )


def get_all_competitions_desc() -> list[dict]:
    """Every meet result, most recent first - used by the /competitions list."""
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM competitions ORDER BY competition_date DESC, created_at DESC"
        ).fetchall()
    return rows


def get_competition_by_id(competition_id: str) -> dict | None:
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM competitions WHERE id = ?", (competition_id,)
        ).fetchone()
        return row


def count_competitions() -> int:
    with connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM competitions").fetchone()
    return row["n"] if row else 0


def delete_competition(competition_id: str) -> bool:
    """Deletes a single meet result by id. Returns True if a row was removed."""
    with connection() as conn:
        cur = conn.execute("DELETE FROM competitions WHERE id = ?", (competition_id,))
        return cur.rowcount > 0
