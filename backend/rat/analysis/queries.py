"""Answering metric questions from the stored tables.

Everything here reads SQLite only: the heavy parsing already happened
during analysis. The public entry points are `object_metrics`,
`object_history`, `list_commits` and `list_authors`; the HTTP layer in
`rat/api/metrics.py` is a thin wrapper around them.

The interesting part is turning a user's filters into one commit set H:

- time range      -> committer_ts >= from AND committer_ts < to  (to is exclusive)
- author          -> that author's commits (email or name matched)
- manual hashes   -> the intersection of the picked hashes with what we stored
- as-of commit    -> every commit reachable from the reference commit,
                     walked over `commit_graph` (which includes merge
                     commits, so the walk never stops early)

All filters AND together, so they compose freely (spec item 49).
"""
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .. import db


class UnknownCommit(Exception):
    """The referenced commit hash is not part of the analysed history."""


class UnknownObject(Exception):
    """The queried path was never touched in the repository's history."""


@dataclass
class Filters:
    """The user-selected commit-set filters, already parsed."""

    author: Optional[str] = None
    from_ts: Optional[int] = None       # inclusive, unix seconds
    to_ts: Optional[int] = None         # exclusive, unix seconds
    as_of: Optional[str] = None         # reference commit hash
    hashes: Optional[list[str]] = None  # manually picked commits


@dataclass
class Resolved:
    """The SQL plus bookkeeping for one resolved commit set H."""

    repo_id: int
    clause: str = ""                    # conditions on the `commits` table
    params: list = field(default_factory=list)
    size: int = 0                       # |H|
    hashes_requested: Optional[int] = None
    hashes_missing: list[str] = field(default_factory=list)


def parse_ts(value: str | int) -> int:
    """Unix seconds ('1700000000') or ISO-8601 ('2024-01-05', '...T00:00:00Z')."""
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if text.lstrip("-").isdigit():
        return int(text)
    moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return int(moment.timestamp())


def _set_sql(resolved: Resolved, column: str = "commit_hash") -> tuple[str, list]:
    """Fragment + params restricting a changes table to the commit set H."""
    inner = "SELECT hash FROM commits WHERE repo_id = ?"
    params: list = [resolved.repo_id]
    if resolved.clause:
        inner += " AND " + resolved.clause
        params.extend(resolved.params)
    return f" AND {column} IN ({inner})", params


def _ancestor_clause(conn, repo_id: int, as_of: str) -> Optional[tuple[str, list[str]]]:
    """Walk ancestors of `as_of` over commit_graph and pick the cheaper side.

    The result is either ('IN', kept hashes), ('NOT IN', excluded hashes) or
    None when `as_of` covers every stored commit (no restriction needed).
    """
    graph_rows = conn.execute(
        "SELECT hash, parents FROM commit_graph WHERE repo_id = ?", (repo_id,)
    ).fetchall()
    graph = {row[0]: row[1].split() if row[1] else [] for row in graph_rows}
    if as_of not in graph:
        raise UnknownCommit(as_of)

    seen = {as_of}
    stack = [as_of]
    while stack:
        for parent in graph.get(stack.pop(), ()):
            if parent not in seen:
                seen.add(parent)
                stack.append(parent)

    stored = [
        row[0]
        for row in conn.execute("SELECT hash FROM commits WHERE repo_id = ?", (repo_id,))
    ]
    kept = [h for h in stored if h in seen]
    if len(kept) == len(stored):
        return None
    excluded = [h for h in stored if h not in seen]
    if len(excluded) < len(kept):
        return "NOT IN", excluded
    return "IN", kept


def _resolve(conn, repo_id: int, filters: Filters) -> Resolved:
    """Turn the filters into one clause on the `commits` table (and |H|)."""
    parts: list[str] = []
    params: list = []

    if filters.author:
        parts.append("(author_email = ? OR author_name = ?)")
        params += [filters.author, filters.author]
    if filters.from_ts is not None:
        parts.append("committer_ts >= ?")
        params.append(filters.from_ts)
    if filters.to_ts is not None:
        parts.append("committer_ts < ?")
        params.append(filters.to_ts)

    requested: Optional[int] = None
    missing: list[str] = []
    if filters.hashes is not None:
        wanted = [h.strip() for h in filters.hashes if h.strip()]
        found: list[str] = []
        for hash_ in wanted:
            row = conn.execute(
                "SELECT 1 FROM commits WHERE repo_id = ? AND hash = ?", (repo_id, hash_)
            ).fetchone()
            (found if row else missing).append(hash_)
        requested = len(wanted)
        parts.append("hash IN (SELECT value FROM json_each(?))")
        params.append(json.dumps(found))

    if filters.as_of:
        ancestors = _ancestor_clause(conn, repo_id, filters.as_of)
        if ancestors is not None:
            operator, hashes = ancestors
            parts.append(f"hash {operator} (SELECT value FROM json_each(?))")
            params.append(json.dumps(sorted(hashes)))

    clause = " AND ".join(parts)
    count_sql = "SELECT COUNT(*) FROM commits WHERE repo_id = ?"
    count_params: list = [repo_id]
    if clause:
        count_sql += " AND " + clause
        count_params += params

    resolved = Resolved(
        repo_id=repo_id,
        clause=clause,
        params=params,
        hashes_requested=requested,
        hashes_missing=missing,
    )
    resolved.size = conn.execute(count_sql, count_params).fetchone()[0]
    return resolved


def _latest_names(conn, repo_id: int) -> dict[str, str]:
    """Most recent display name per author email (newest commit wins)."""
    names: dict[str, str] = {}
    rows = conn.execute(
        "SELECT author_email, author_name FROM commits WHERE repo_id = ?"
        " ORDER BY committer_ts DESC, hash",
        (repo_id,),
    )
    for email, name in rows:
        names.setdefault(email, name)
    return names


def _author_slices(conn, resolved: Resolved, table: str, path: str,
                   total_churn: int) -> list[dict]:
    """Per-author breakdown of one object over H (spec items 36-39).

    The commit set lives in the subquery, so an author's row-less commits
    (empty commits, binary-only commits) still count toward `commits`,
    while `touched` excludes authors with no rows on this object at all.
    """
    clause_sql = " AND " + resolved.clause if resolved.clause else ""
    rows = conn.execute(
        f"SELECT c.author_email AS email,"
        f" COUNT(DISTINCT c.hash) AS commits,"
        f" COUNT(DISTINCT CASE WHEN f.added + f.removed > 0 THEN c.hash END) AS modifications,"
        f" COALESCE(SUM(f.added), 0) AS added,"
        f" COALESCE(SUM(f.removed), 0) AS removed,"
        f" COUNT(f.commit_hash) AS touched"
        f" FROM (SELECT hash, repo_id, author_email FROM commits"
        f"       WHERE repo_id = ?{clause_sql}) AS c"
        f" LEFT JOIN {table} AS f"
        f"  ON f.repo_id = c.repo_id AND f.commit_hash = c.hash AND f.path = ?"
        f" GROUP BY c.author_email"
        f" HAVING touched > 0"
        f" ORDER BY (added + removed) DESC, email",
        [resolved.repo_id, *resolved.params, path],
    ).fetchall()

    names = _latest_names(conn, resolved.repo_id)
    slices: list[dict] = []
    for row in rows:
        churn = row["added"] + row["removed"]
        slices.append({
            "name": names.get(row["email"], row["email"]),
            "email": row["email"],
            "commits": row["commits"],
            "modifications": row["modifications"],
            "added": row["added"],
            "removed": row["removed"],
            "churn": churn,
            "ownership": round(churn / total_churn, 4) if total_churn else 0.0,
        })
    return slices


def _children(conn, resolved: Resolved, path: str) -> list[dict]:
    """Immediate children (files and directories) of directory `path`.

    A child directory's numbers are its whole-subtree rollup, which is
    exactly what dir_changes stores for its path already.
    """
    base = "" if path == "" else path + "/"
    n = len(base)
    set_sql, set_params = _set_sql(resolved, "f.commit_hash")
    params = [resolved.repo_id, n, base, n, *set_params]

    children: dict[str, dict] = {}
    for table, kind in (("dir_changes", "dir"), ("file_changes", "file")):
        rows = conn.execute(
            f"SELECT f.path AS path,"
            f" SUM(f.added) AS added,"
            f" SUM(f.removed) AS removed,"
            f" COUNT(DISTINCT CASE WHEN f.added + f.removed > 0 THEN f.commit_hash END)"
            f"   AS modifications"
            f" FROM {table} AS f"
            f" WHERE f.repo_id = ? AND substr(f.path, 1, ?) = ?"
            f"   AND instr(substr(f.path, ? + 1), '/') = 0"
            f"{set_sql}"
            f" GROUP BY f.path",
            params,
        ).fetchall()
        for row in rows:
            name = row["path"][n:]
            if not name or name in children:
                continue  # skip the object's own rollup row and duplicates
            children[name] = {
                "kind": kind,
                "path": row["path"],
                "added": row["added"],
                "removed": row["removed"],
                "growth": row["added"] - row["removed"],
                "churn": row["added"] + row["removed"],
                "modifications": row["modifications"],
            }
    return [children[name] for name in sorted(children)]


def _require_object(conn, repo_id: int, kind: str, path: str) -> None:
    """404-guard: the path must appear somewhere in the stored history."""
    if kind == "dir" and path == "":
        return  # the repository root always exists
    table = "file_changes" if kind == "file" else "dir_changes"
    row = conn.execute(
        f"SELECT 1 FROM {table} WHERE repo_id = ? AND path = ? LIMIT 1", (repo_id, path)
    ).fetchone()
    if row is None:
        raise UnknownObject(f"{kind} '{path}'")


def object_metrics(repo_id: int, kind: str, path: str, filters: Filters) -> dict:
    """All metrics for one object (file, directory, or root) over H."""
    table = "file_changes" if kind == "file" else "dir_changes"
    with db.connection() as conn:
        resolved = _resolve(conn, repo_id, filters)
        _require_object(conn, repo_id, kind, path)
        set_sql, set_params = _set_sql(resolved)
        added, removed, modifications = conn.execute(
            f"SELECT COALESCE(SUM(f.added), 0),"
            f" COALESCE(SUM(f.removed), 0),"
            f" COUNT(DISTINCT CASE WHEN f.added + f.removed > 0 THEN f.commit_hash END)"
            f" FROM {table} AS f"
            f" WHERE f.repo_id = ? AND f.path = ?{set_sql}",
            [repo_id, path, *set_params],
        ).fetchone()
        churn = added + removed
        authors = _author_slices(conn, resolved, table, path, churn)
        children = _children(conn, resolved, path) if kind == "dir" else []

    size = resolved.size
    return {
        "repo_id": repo_id,
        "kind": kind,
        "path": path,
        "set": {
            "commit_count": size,
            "from_ts": filters.from_ts,
            "to_ts": filters.to_ts,
            "author": filters.author,
            "as_of": filters.as_of,
            "hashes_requested": resolved.hashes_requested,
            "hashes_missing": resolved.hashes_missing,
        },
        "added": added,
        "removed": removed,
        "growth": added - removed,
        "churn": churn,
        "modifications": modifications,
        "modification_frequency": round(modifications / size, 4) if size else 0.0,
        "churn_rate": round(churn / size, 4) if size else 0.0,
        "authors": authors,
        "children": children,
    }


def object_history(repo_id: int, kind: str, path: str, filters: Filters,
                   limit: int, offset: int) -> dict:
    """The per-commit rows behind one object's numbers (newest first)."""
    table = "file_changes" if kind == "file" else "dir_changes"
    with db.connection() as conn:
        resolved = _resolve(conn, repo_id, filters)
        _require_object(conn, repo_id, kind, path)
        set_sql, set_params = _set_sql(resolved, "f.commit_hash")
        total = conn.execute(
            f"SELECT COUNT(*) FROM {table} AS f"
            f" WHERE f.repo_id = ? AND f.path = ?{set_sql}",
            [repo_id, path, *set_params],
        ).fetchone()[0]
        rows = conn.execute(
            f"SELECT c.hash, c.committer_ts, c.author_name, c.author_email,"
            f" f.added, f.removed"
            f" FROM {table} AS f"
            f" JOIN commits AS c ON c.repo_id = f.repo_id AND c.hash = f.commit_hash"
            f" WHERE f.repo_id = ? AND f.path = ?{set_sql}"
            f" ORDER BY c.committer_ts DESC, c.hash LIMIT ? OFFSET ?",
            [repo_id, path, *set_params, limit, offset],
        ).fetchall()

    items = [
        {
            "hash": row["hash"],
            "committer_ts": row["committer_ts"],
            "author_name": row["author_name"],
            "author_email": row["author_email"],
            "added": row["added"],
            "removed": row["removed"],
            "growth": row["added"] - row["removed"],
            "churn": row["added"] + row["removed"],
        }
        for row in rows
    ]
    return {
        "repo_id": repo_id,
        "kind": kind,
        "path": path,
        "total": total,
        "items": items,
    }


def list_commits(repo_id: int, limit: int, offset: int) -> dict:
    """All measured commits of a repo, newest first (for the commit picker)."""
    with db.connection() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM commits WHERE repo_id = ?", (repo_id,)
        ).fetchone()[0]
        rows = conn.execute(
            "SELECT c.hash, c.committer_ts, c.author_name, c.author_email, c.parents,"
            " COALESCE(f.added, 0) AS added,"
            " COALESCE(f.removed, 0) AS removed,"
            " COALESCE(f.files, 0) AS files_changed"
            " FROM commits AS c"
            " LEFT JOIN ("
            "   SELECT commit_hash, SUM(added) AS added, SUM(removed) AS removed,"
            "          COUNT(*) AS files"
            "   FROM file_changes WHERE repo_id = ? GROUP BY commit_hash"
            " ) AS f ON f.commit_hash = c.hash"
            " WHERE c.repo_id = ?"
            " ORDER BY c.committer_ts DESC, c.hash LIMIT ? OFFSET ?",
            (repo_id, repo_id, limit, offset),
        ).fetchall()
    return {"repo_id": repo_id, "total": total, "items": [dict(row) for row in rows]}


def list_authors(repo_id: int, limit: int) -> dict:
    """All authors with their totals over the whole history (author filter UI)."""
    with db.connection() as conn:
        total = conn.execute(
            "SELECT COUNT(DISTINCT author_email) FROM commits WHERE repo_id = ?",
            (repo_id,),
        ).fetchone()[0]
        rows = conn.execute(
            "SELECT c.author_email AS email,"
            " COUNT(DISTINCT c.hash) AS commits,"
            " COALESCE(SUM(f.added), 0) AS added,"
            " COALESCE(SUM(f.removed), 0) AS removed,"
            " MIN(c.committer_ts) AS first_ts,"
            " MAX(c.committer_ts) AS last_ts"
            " FROM commits AS c"
            " LEFT JOIN file_changes AS f"
            "  ON f.repo_id = c.repo_id AND f.commit_hash = c.hash"
            " WHERE c.repo_id = ?"
            " GROUP BY c.author_email"
            " ORDER BY commits DESC, email LIMIT ?",
            (repo_id, limit),
        ).fetchall()
        names = _latest_names(conn, repo_id)

    items = []
    for row in rows:
        item = dict(row)
        item["name"] = names.get(row["email"], row["email"])
        items.append(item)
    return {"repo_id": repo_id, "total": total, "items": items}
