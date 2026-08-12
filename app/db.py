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
    """Creates tables from schema.sql if they don't already exist."""
    sql = config.SCHEMA_SQL_PATH.read_text()
    with connection() as conn:
        conn.executescript(sql)


def load_manifest() -> list[dict]:
    return json.loads(config.SCHEMA_MANIFEST_PATH.read_text())["columns"]


def entry_columns() -> list[str]:
    return [c["column"] for c in load_manifest()]


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
