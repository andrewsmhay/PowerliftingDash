"""SQLite access layer. One connection per request via FastAPI dependency;
WAL mode so the background sync job and web requests don't block each other.
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


def record_sync_result(status: str, message: str) -> None:
    update_settings(
        last_sync_at=datetime.now(timezone.utc).isoformat(),
        last_sync_status=status,
        last_sync_message=message,
    )


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
