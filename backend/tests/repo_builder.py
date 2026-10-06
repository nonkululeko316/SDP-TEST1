"""Builds the small scenario repository shared by the engine and API tests.

Timeline (committer dates are 10:00 UTC on consecutive January days, so
date-filter tests can use plain dates):

  c1  Jan 1  Alice  README.md (2 lines) + src/app.py (3 lines)   [initial commit]
  c2  Jan 2  Alice  one line added to README.md
  c3  Jan 3  Bob    src/app.py renamed to src/main.py plus 1 added line
  c4  Jan 4  Bob    README.md renamed to README.rst, no content change (pure rename, 0/0)
  c5  Jan 5  Bob    README.rst deleted (0/3)
  c6  Jan 6  Alice  a binary file is added (must be invisible to the metrics)
  c7  Jan 7  Alice  a commit with no changes (--allow-empty)
  c8  Jan 8  Bob    +1 line in src/main.py, made on a side branch
  merge Jan 9 Bob   the side branch is merged back (--no-ff; must be ignored)

Totals over all 8 non-merge commits: +8 / -3 lines.
"""
import os
import subprocess
from pathlib import Path

ALICE = {"name": "Alice", "email": "alice@example.com"}
BOB = {"name": "Bob", "email": "bob@example.com"}


def git(repo: Path, *args: str, name: str = "Alice", email: str = "alice@example.com",
        date: str | None = None) -> str:
    """Run one git command in the fixture repo with a fixed identity/date."""
    cmd = [
        "git", "-C", str(repo),
        "-c", f"user.name={name}", "-c", f"user.email={email}",
        "-c", "commit.gpgsign=false",
        *args,
    ]
    env = None
    if date is not None:
        env = os.environ | {"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
    return subprocess.run(cmd, capture_output=True, text=True, check=True, env=env).stdout.strip()


def commit(repo: Path, message: str, *, name: str = "Alice", email: str = "alice@example.com",
           date: str | None = None) -> str:
    """Stage everything, commit, and return the new commit hash."""
    git(repo, "add", "-A", name=name, email=email)
    git(repo, "commit", "-m", message, name=name, email=email, date=date)
    return git(repo, "rev-parse", "HEAD", name=name, email=email)


def _at(day: int) -> str:
    return f"2024-01-0{day}T10:00:00+00:00"


def build_repo(root: Path) -> dict[str, str]:
    """Create the scenario repository under `root`; return hashes by label."""
    repo = root / "sample"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    hashes: dict[str, str] = {}

    # c1: two new files, five added lines in total.
    (repo / "README.md").write_text("hello\nworld\n")
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("a\nb\nc\n")
    hashes["c1"] = commit(repo, "initial commit", date=_at(1))

    # c2: one line added to README.md.
    with (repo / "README.md").open("a") as handle:
        handle.write("more\n")
    hashes["c2"] = commit(repo, "expand readme", date=_at(2))

    # c3: rename + one added line (must be one rename entry, not delete+add).
    git(repo, "mv", "src/app.py", "src/main.py", **BOB)
    with (repo / "src" / "main.py").open("a") as handle:
        handle.write("d\n")
    hashes["c3"] = commit(repo, "rename app to main", date=_at(3), **BOB)

    # c4: pure rename; content unchanged.
    git(repo, "mv", "README.md", "README.rst", **BOB)
    hashes["c4"] = commit(repo, "rename readme", date=_at(4), **BOB)

    # c5: deletion of the three-line README.rst.
    git(repo, "rm", "README.rst", **BOB)
    hashes["c5"] = commit(repo, "drop readme", date=_at(5), **BOB)

    # c6: binary file.
    (repo / "blob.bin").write_bytes(bytes(range(256)) * 4)
    hashes["c6"] = commit(repo, "add binary", date=_at(6))

    # c7: empty commit.
    git(repo, "commit", "--allow-empty", "-m", "empty commit", date=_at(7))
    hashes["c7"] = git(repo, "rev-parse", "HEAD")

    # c8 on a side branch, then merged back in the merge commit.
    git(repo, "checkout", "-b", "feature", **BOB)
    with (repo / "src" / "main.py").open("a") as handle:
        handle.write("e\n")
    hashes["c8"] = commit(repo, "feature work", date=_at(8), **BOB)

    git(repo, "checkout", "main", **BOB)
    git(repo, "merge", "--no-ff", "-m", "merge feature", "feature", date=_at(9), **BOB)
    hashes["merge"] = git(repo, "rev-parse", "HEAD")

    return hashes
