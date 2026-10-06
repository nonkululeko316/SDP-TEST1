"""Streaming parser for the raw `git log --numstat -z` byte stream.

We shell out to git instead of re-implementing diffing: git already
implements exactly the semantics the spec requires (50% rename
detection, binary detection, line counts) and is much faster than a
Python diff would be.

Wire format (verified empirically against git 2.43 -- see tests):

    __C__ NUL <hash> NUL <parents> NUL <unix-ts> NUL <name> NUL <email> NUL LF
    ( <added> TAB <removed> TAB <path> NUL )*
    ( <added> TAB <removed> TAB NUL <old-path> NUL <new-path> NUL )*   # renames

Notes:
- Binary entries use '-' for both counts and are dropped by the parser.
- Rename entries carry the old and new path as separate tokens; only the
  *new* path is recorded (the spec attributes changes to the new path).
- The single LF after each commit header glues onto the next token and is
  stripped during parsing.
"""
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Iterator, Optional

MAGIC = b"__C__"
_ENTRY = re.compile(rb"^(-|\d+)\t(-|\d+)\t(.*)$", re.S)


class GitLogError(Exception):
    """`git log` failed (not a repository, git missing, ...)."""


@dataclass
class CommitDiff:
    """Metadata and per-file line changes for one non-merge commit."""

    hash: str
    parents: str
    committer_ts: int
    author_name: str
    author_email: str
    files: list[tuple[str, int, int]] = field(default_factory=list)


def stream_commits(repo_root: Path) -> Iterator[CommitDiff]:
    """Yield a CommitDiff per non-merge commit reachable from HEAD (newest first)."""
    cmd = [
        "git", "-C", str(repo_root),
        "log", "--no-merges", "-M50%", "--numstat", "-z", "--no-show-signature",
        "--format=__C__%x00%H%x00%P%x00%ct%x00%an%x00%ae",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stream = proc.stdout
    assert stream is not None
    try:
        yield from _parse(stream, proc)
    finally:
        stream.close()
        if proc.poll() is None:
            proc.kill()
        proc.wait()


def _parse(stream: BinaryIO, proc: subprocess.Popen) -> Iterator[CommitDiff]:
    current: Optional[CommitDiff] = None
    meta: list[str] = []
    meta_left = 0
    awaiting: Optional[tuple[Optional[int], Optional[int]]] = None
    rename_seen: list[str] = []

    for token in _tokens(stream):
        if meta_left > 0:
            # Header fields, in order: hash, parents, ct, name, email.
            meta.append(_text(token))
            meta_left -= 1
            if meta_left == 0:
                current = CommitDiff(
                    hash=meta[0],
                    parents=meta[1],
                    committer_ts=int(meta[2] or "0"),
                    author_name=meta[3],
                    author_email=meta[4],
                )
            continue

        if awaiting is not None:
            # Rename: second path token completes the entry.
            rename_seen.append(_text(token))
            if len(rename_seen) == 2:
                _record(current, rename_seen[1], *awaiting)
                awaiting, rename_seen = None, []
            continue

        if token.startswith(b"\n"):
            token = token[1:]
            if not token:
                continue

        if token == MAGIC:
            if current is not None:
                yield current
            meta, meta_left = [], 5
            continue

        match = _ENTRY.match(token)
        if match is None:
            raise GitLogError(f"Unexpected output from git log: {token[:120]!r}")
        added, removed = _count(match.group(1)), _count(match.group(2))
        path = match.group(3)
        if path:
            _record(current, _text(path), added, removed)
        else:
            # Rename entries have an empty path field; two path tokens follow.
            awaiting = (added, removed)

    if current is not None:
        yield current

    rc = proc.wait()
    if rc != 0 and proc.stderr is not None:
        tail = _text(proc.stderr.read()).strip()[-500:]
        raise GitLogError(f"git log exited with status {rc}: {tail}")


def _tokens(stream: BinaryIO) -> Iterator[bytes]:
    """Split the NUL-separated stream into raw tokens (chunk-boundary safe)."""
    buf = b""
    while True:
        chunk = stream.read(1 << 20)
        if not chunk:
            break
        buf += chunk
        while True:
            idx = buf.find(b"\x00")
            if idx == -1:
                break
            yield buf[:idx]
            buf = buf[idx + 1:]
    if buf:
        yield buf


def _record(commit: Optional[CommitDiff], path: str,
            added: Optional[int], removed: Optional[int]) -> None:
    """Store one file change; binary entries (None counts) are not measured."""
    if commit is None or added is None or removed is None:
        return
    commit.files.append((path, added, removed))


def _count(raw: bytes) -> Optional[int]:
    return None if raw == b"-" else int(raw)


def _text(raw: bytes) -> str:
    return raw.decode("utf-8", "replace")
