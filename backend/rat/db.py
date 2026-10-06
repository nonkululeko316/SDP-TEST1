"""SQLite storage: the repository registry and the computed metrics."""
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
    status      TEXT NOT NULL,       -- queued | ingesting | analysing | ready | error
    message     TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
)
"""

_METRICS_SCHEMA = """
CREATE TABLE IF NOT EXISTS commits (
    repo_id          INTEGER NOT NULL,
    hash             TEXT NOT NULL,
    parents          TEXT NOT NULL,      -- space-separated parent hashes, '' for root commits
    author_name      TEXT NOT NULL,      -- resolved identity (mailmap + manual merges)
    author_email     TEXT NOT NULL,      -- resolved identity (mailmap + manual merges)
    raw_author_name  TEXT,               -- exactly as git reported it
    raw_author_email TEXT,
    committer_ts     INTEGER NOT NULL,   -- unix timestamp of the committer date
    PRIMARY KEY (repo_id, hash)
);
CREATE INDEX IF NOT EXISTS idx_commits_time ON commits (repo_id, committer_ts);

CREATE TABLE IF NOT EXISTS file_changes (
    repo_id     INTEGER NOT NULL,
    commit_hash TEXT NOT NULL,
    path        TEXT NOT NULL,
    added       INTEGER NOT NULL,
    removed     INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_file_changes_path ON file_changes (repo_id, path);
CREATE INDEX IF NOT EXISTS idx_file_changes_commit ON file_changes (repo_id, commit_hash);

CREATE TABLE IF NOT EXISTS dir_changes (
    repo_id     INTEGER NOT NULL,
    commit_hash TEXT NOT NULL,
    path        TEXT NOT NULL,       -- directory path, '' = repository root
    added       INTEGER NOT NULL,
    removed     INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dir_changes_path ON dir_changes (repo_id, path);
CREATE INDEX IF NOT EXISTS idx_dir_changes_commit ON dir_changes (repo_id, commit_hash);

CREATE TABLE IF NOT EXISTS commit_graph (
    repo_id INTEGER NOT NULL,
    hash    TEXT NOT NULL,
    parents TEXT NOT NULL,           -- space-separated parents, '' for the root commit
    PRIMARY KEY (repo_id, hash)
);

CREATE TABLE IF NOT EXISTS author_merges (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id      INTEGER NOT NULL,
    source_email TEXT NOT NULL,      -- identity that disappears (resolved email)
    target_email TEXT NOT NULL,      -- identity it merges into (resolved email)
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_author_merges_repo ON author_merges (repo_id);
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """Upgrade databases created before later schema versions.

    The raw author columns were added in Chunk 4; existing databases get
    them back-filled (raw = resolved) by the next author resolution pass.
    """
    columns = {row[1] for row in conn.execute("PRAGMA table_info(commits)")}
    if not columns:
        return
    if "raw_author_name" not in columns:
        conn.execute("ALTER TABLE commits ADD COLUMN raw_author_name TEXT")
    if "raw_author_email" not in columns:
        conn.execute("ALTER TABLE commits ADD COLUMN raw_author_email TEXT")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_commits_raw ON commits (repo_id, raw_author_email)"
    )


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
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
    with connection() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA)
        conn.executescript(_METRICS_SCHEMA)
        _migrate(conn)


def create_repo(name: str, source_type: str, source_ref: str) -> dict:
    """Insert a new repository row in the 'queued' state and return it."""
    now = datetime.now(timezone.utc).isoformat()
    with connection() as conn:
        cur = conn.execute(
            "INSERT INTO repositories (name, source_type, source_ref, status, created_at)"
            " VALUES (?, ?, ?, 'queued', ?)",
            (name, source_type, source_ref, now),
        )
        repo_id = cur.lastrowid
    return get_repo(repo_id)


def get_repo(repo_id: int) -> Optional[dict]:
    """One repository row, or None if it does not exist."""
    with connection() as conn:
        row = conn.execute("SELECT * FROM repositories WHERE id = ?", (repo_id,)).fetchone()
    return dict(row) if row else None


def list_repos() -> list[dict]:
    """All repository rows, oldest first."""
    with connection() as conn:
        rows = conn.execute("SELECT * FROM repositories ORDER BY id").fetchall()
    return [dict(row) for row in rows]


def update_repo(repo_id: int, **fields: Any) -> None:
    """Update whitelisted columns (name, local_path, status, message)."""
    allowed = {"name", "local_path", "status", "message"}
    updates = {key: value for key, value in fields.items() if key in allowed}
    if not updates:
        return
    assignments = ", ".join(f"{key} = ?" for key in updates)
    with connection() as conn:
        conn.execute(
            f"UPDATE repositories SET {assignments} WHERE id = ?",  # keys are whitelisted above
            (*updates.values(), repo_id),
        )
