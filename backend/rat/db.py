"""A tiny SQLite registry that keeps track of the repositories we know about."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator, Optional

from . import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS repositories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    source_type TEXT NOT NULL,       -- 'zip' or 'url'
    source_ref  TEXT NOT NULL,       -- original filename or URL
    local_path  TEXT,                -- where the repo lives on disk (set after ingestion)
    status      TEXT NOT NULL,       -- queued | ingesting | ingested | error
    message     TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
)
"""


@contextmanager
def _connection() -> Iterator[sqlite3.Connection]:
    """One short-lived connection per call; commits on success, always closes."""
    conn = sqlite3.connect(config.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Create the data folders (if needed) and the registry table."""
    config.ensure_dirs()
    with _connection() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(_SCHEMA)


def create_repo(name: str, source_type: str, source_ref: str) -> dict:
    """Insert a new repository row in the 'queued' state and return it."""
    now = datetime.now(timezone.utc).isoformat()
    with _connection() as conn:
        cur = conn.execute(
            "INSERT INTO repositories (name, source_type, source_ref, status, created_at)"
            " VALUES (?, ?, ?, 'queued', ?)",
            (name, source_type, source_ref, now),
        )
        repo_id = cur.lastrowid
    return get_repo(repo_id)


def get_repo(repo_id: int) -> Optional[dict]:
    """One repository row, or None if it does not exist."""
    with _connection() as conn:
        row = conn.execute("SELECT * FROM repositories WHERE id = ?", (repo_id,)).fetchone()
    return dict(row) if row else None


def list_repos() -> list[dict]:
    """All repository rows, oldest first."""
    with _connection() as conn:
        rows = conn.execute("SELECT * FROM repositories ORDER BY id").fetchall()
    return [dict(row) for row in rows]


def update_repo(repo_id: int, **fields: Any) -> None:
    """Update whitelisted columns (name, local_path, status, message)."""
    allowed = {"name", "local_path", "status", "message"}
    updates = {key: value for key, value in fields.items() if key in allowed}
    if not updates:
        return
    assignments = ", ".join(f"{key} = ?" for key in updates)
    with _connection() as conn:
        conn.execute(
            f"UPDATE repositories SET {assignments} WHERE id = ?",  # keys are whitelisted above
            (*updates.values(), repo_id),
        )
