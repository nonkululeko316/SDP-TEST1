"""Author identity resolution: `.mailmap` plus manual merge overrides.

Every commit row keeps two identities:

- `raw_author_name` / `raw_author_email`: exactly what git reported;
- `author_name` / `author_email`: the *resolved* identity that every
  query uses (spec item 36: the authorship test uses the identity
  after merging).

Resolution is a two-stage pipeline applied to each raw identity:

1. **git mailmap** - `git check-mailmap` applies the repository's
   `.mailmap` file (spec item 46), batched over all distinct authors in
   one subprocess call.
2. **manual merges** - links stored in the `author_merges` table (spec
   item 47) are applied on top, so they work with or without a mailmap
   and always act as an override.

`resolve_authors()` re-materialises the resolved columns for one
repository. It runs after every analysis and after every manual merge
change, so queries never need to know about either mechanism.
"""
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .. import db

_CONTACT = re.compile(r"^(?P<name>.*?)\s*<(?P<email>[^<>]*)>$")


def _mailmap_map(repo_root: Optional[Path],
                 pairs: list[tuple[str, str]]) -> dict[tuple[str, str], tuple[str, str]]:
    """Apply the repo's .mailmap: raw (name, email) -> canonical (name, email).

    Only pairs whose canonical form differs are returned. If git fails or
    the output does not line up one-to-one, resolution quietly falls back
    to the raw identities (no mailmap).
    """
    if not pairs or repo_root is None:
        return {}
    contacts = "".join(f"{name} <{email}>\n" for name, email in pairs)
    result = subprocess.run(
        ["git", "-C", str(repo_root), "check-mailmap", "--stdin"],
        input=contacts, capture_output=True, text=True,
    )
    if result.returncode != 0:
        return {}
    lines = result.stdout.splitlines()
    if len(lines) != len(pairs):
        return {}

    mapping: dict[tuple[str, str], tuple[str, str]] = {}
    for raw, line in zip(pairs, lines):
        match = _CONTACT.match(line.strip())
        if match is None:
            continue
        canonical = (match.group("name"), match.group("email"))
        if canonical != raw:
            mapping[raw] = canonical
    return mapping


def _links(repo_id: int) -> dict[str, str]:
    """Direct manual merge links: source resolved email -> target email."""
    with db.connection() as conn:
        rows = conn.execute(
            "SELECT source_email, target_email FROM author_merges WHERE repo_id = ?",
            (repo_id,),
        ).fetchall()
    return {row[0]: row[1] for row in rows}


def _final_email(email: str, links: dict[str, str]) -> str:
    """Follow a merge chain to its end (cycle-safe)."""
    seen: set[str] = set()
    while email in links and email not in seen:
        seen.add(email)
        email = links[email]
    return email


def resolve_map(repo_id: int,
                repo_root: Optional[Path]) -> dict[tuple[str, str], tuple[str, str]]:
    """Every distinct raw identity and its final resolved identity.

    With no mailmap and no manual merges this is the identity mapping
    (raw -> raw), which keeps the common case a no-op.
    """
    with db.connection() as conn:
        pairs = [
            (row[0], row[1])
            for row in conn.execute(
                "SELECT DISTINCT COALESCE(raw_author_name, author_name),"
                " COALESCE(raw_author_email, author_email)"
                " FROM commits WHERE repo_id = ?",
                (repo_id,),
            )
        ]
    mailmap = _mailmap_map(repo_root, pairs)
    links = _links(repo_id)

    resolved: dict[tuple[str, str], tuple[str, str]] = {}
    for raw in pairs:
        name, email = mailmap.get(raw, raw)
        resolved[raw] = (name, _final_email(email, links))
    return resolved


def resolve_authors(repo_id: int, repo_root: Optional[Path]) -> dict:
    """Re-materialise the resolved author columns; returns small stats.

    Always resets the resolved columns to raw first and then applies the
    current mapping, so deleting a manual merge restores the old state.
    """
    with db.connection() as conn:
        # Back-fill raw columns for databases migrated from Chunk 3.
        conn.execute(
            "UPDATE commits SET raw_author_name = author_name,"
            " raw_author_email = author_email"
            " WHERE repo_id = ? AND raw_author_name IS NULL",
            (repo_id,),
        )

    mapping = resolve_map(repo_id, repo_root)
    updates = [
        (final_name, final_email, repo_id, raw_name, raw_email)
        for (raw_name, raw_email), (final_name, final_email) in mapping.items()
        if (final_name, final_email) != (raw_name, raw_email)
    ]

    with db.connection() as conn:
        conn.execute(
            "UPDATE commits SET author_name = raw_author_name,"
            " author_email = raw_author_email WHERE repo_id = ?",
            (repo_id,),
        )
        if updates:
            conn.executemany(
                "UPDATE commits SET author_name = ?, author_email = ?"
                " WHERE repo_id = ? AND raw_author_name = ? AND raw_author_email = ?",
                updates,
            )

    resolved_emails = {final_email for _, final_email in mapping.values()}
    # "merged" counts raw emails folded into a different email (mailmap or
    # manual merge); name-only changes and plain name variants do not count.
    folded = {
        raw_email
        for (_, raw_email), (_, final_email) in mapping.items()
        if final_email != raw_email
    }
    return {
        "identities": len(mapping),
        "resolved": len(resolved_emails),
        "merged": len(folded),
    }


def list_merges(repo_id: int) -> list[dict]:
    """All manual merges of a repository, oldest first."""
    with db.connection() as conn:
        rows = conn.execute(
            "SELECT id, repo_id, source_email, target_email, created_at"
            " FROM author_merges WHERE repo_id = ? ORDER BY id",
            (repo_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def add_merge(repo_id: int, source_email: str, target_email: str) -> dict:
    """Store one manual merge link and return its row."""
    now = datetime.now(timezone.utc).isoformat()
    with db.connection() as conn:
        cur = conn.execute(
            "INSERT INTO author_merges (repo_id, source_email, target_email, created_at)"
            " VALUES (?, ?, ?, ?)",
            (repo_id, source_email, target_email, now),
        )
        merge_id = cur.lastrowid
    return {
        "id": merge_id,
        "repo_id": repo_id,
        "source_email": source_email,
        "target_email": target_email,
        "created_at": now,
    }


def remove_merge(repo_id: int, merge_id: int) -> bool:
    """Delete one manual merge; True if a row was removed."""
    with db.connection() as conn:
        cur = conn.execute(
            "DELETE FROM author_merges WHERE id = ? AND repo_id = ?",
            (merge_id, repo_id),
        )
        return cur.rowcount > 0
