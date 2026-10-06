"""Scenario test for the metric engine on a small, hand-built repository.

The fixture repo exercises, in order:

  c1  initial commit adding README.md (2 lines) and src/app.py (3 lines)
  c2  one line added to README.md
  c3  src/app.py renamed to src/main.py plus one added line
  c4  README.md renamed to README.rst without a content change (0/0)
  c5  README.rst deleted (the three lines go back out)
  c6  a binary file is added (must be invisible to the metrics)
  c7  an empty commit (counted, but with no file rows)
  c8  a commit on a side branch, merged back as c9 (the merge must be ignored)

Expected totals: 8 commits, 7 file rows, +8 / -3 lines, and directory
rollups that agree with the per-file rows.
"""
import subprocess
from pathlib import Path

from rat import db
from rat.analysis.engine import analyse_repo
from rat.analysis.store import ancestors


def git(repo: Path, *args: str, name: str = "Alice", email: str = "alice@example.com") -> str:
    """Run one git command in the fixture repo with a fixed identity."""
    cmd = [
        "git", "-C", str(repo),
        "-c", f"user.name={name}", "-c", f"user.email={email}",
        "-c", "commit.gpgsign=false",
        *args,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()


def commit(repo: Path, message: str, *, name: str = "Alice", email: str = "alice@example.com") -> str:
    """Stage everything, commit, and return the new commit hash."""
    git(repo, "add", "-A", name=name, email=email)
    git(repo, "commit", "-m", message, name=name, email=email)
    return git(repo, "rev-parse", "HEAD", name=name, email=email)


def build_repo(root: Path) -> dict[str, str]:
    """Create the scenario repository under `root`; return commit hashes by label."""
    repo = root / "sample"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    hashes: dict[str, str] = {}

    # c1: two new files, five added lines in total.
    (repo / "README.md").write_text("hello\nworld\n")
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("a\nb\nc\n")
    hashes["c1"] = commit(repo, "initial commit")

    # c2: one line added to README.md.
    with (repo / "README.md").open("a") as handle:
        handle.write("more\n")
    hashes["c2"] = commit(repo, "expand readme")

    # c3: rename + one added line (must be one rename entry, not delete+add).
    git(repo, "mv", "src/app.py", "src/main.py", name="Bob", email="bob@example.com")
    with (repo / "src" / "main.py").open("a") as handle:
        handle.write("d\n")
    hashes["c3"] = commit(repo, "rename app to main", name="Bob", email="bob@example.com")

    # c4: pure rename; content unchanged.
    git(repo, "mv", "README.md", "README.rst", name="Bob", email="bob@example.com")
    hashes["c4"] = commit(repo, "rename readme", name="Bob", email="bob@example.com")

    # c5: deletion of the three-line README.rst.
    git(repo, "rm", "README.rst", name="Bob", email="bob@example.com")
    hashes["c5"] = commit(repo, "drop readme", name="Bob", email="bob@example.com")

    # c6: binary file.
    (repo / "blob.bin").write_bytes(bytes(range(256)) * 4)
    hashes["c6"] = commit(repo, "add binary")

    # c7: empty commit.
    git(repo, "commit", "--allow-empty", "-m", "empty commit")
    hashes["c7"] = git(repo, "rev-parse", "HEAD")

    # c8 on a side branch, then merged back in c9.
    git(repo, "checkout", "-b", "feature", name="Bob", email="bob@example.com")
    with (repo / "src" / "main.py").open("a") as handle:
        handle.write("e\n")
    hashes["c8"] = commit(repo, "feature work", name="Bob", email="bob@example.com")

    git(repo, "checkout", "main", name="Bob", email="bob@example.com")
    git(repo, "merge", "--no-ff", "-m", "merge feature", "feature",
        name="Bob", email="bob@example.com")
    hashes["merge"] = git(repo, "rev-parse", "HEAD")

    return hashes


def test_engine_scenario(rat_env):
    repo_path = rat_env / "sample"
    hashes = build_repo(rat_env)
    repo_id = db.create_repo(name="sample", source_type="zip", source_ref="sample.zip")["id"]

    stats = analyse_repo(repo_id, repo_path)
    assert stats["commits"] == 8
    assert stats["file_changes"] == 7

    with db.connection() as conn:
        # Exactly the non-merge commits reachable from HEAD.
        expected = set(git(repo_path, "rev-list", "--no-merges", "HEAD").split())
        stored = {
            row[0]
            for row in conn.execute("SELECT hash FROM commits WHERE repo_id = ?", (repo_id,))
        }
        assert stored == expected
        assert len(stored) == 8
        assert hashes["merge"] not in stored

        # File rows and the root-directory rollup agree: +8 / -3.
        file_totals = conn.execute(
            "SELECT SUM(added), SUM(removed) FROM file_changes WHERE repo_id = ?",
            (repo_id,),
        ).fetchone()
        root_totals = conn.execute(
            "SELECT SUM(added), SUM(removed) FROM dir_changes WHERE repo_id = ? AND path = ''",
            (repo_id,),
        ).fetchone()
        assert tuple(file_totals) == (8, 3)
        assert tuple(root_totals) == (8, 3)

        # The src rollup has one row per commit that touched a file inside it.
        src_rows = conn.execute(
            "SELECT added, removed FROM dir_changes WHERE repo_id = ? AND path = 'src'",
            (repo_id,),
        ).fetchall()
        assert len(src_rows) == 3
        assert sum(row[0] for row in src_rows) == 5
        assert sum(row[1] for row in src_rows) == 0

        # A rename must not delete the old path: src/app.py keeps just its add.
        app_rows = conn.execute(
            "SELECT commit_hash, added, removed FROM file_changes"
            " WHERE repo_id = ? AND path = 'src/app.py'",
            (repo_id,),
        ).fetchall()
        assert [tuple(row) for row in app_rows] == [(hashes["c1"], 3, 0)]

        # The rename target collects c3's and c8's line edits.
        main_rows = conn.execute(
            "SELECT added, removed FROM file_changes WHERE repo_id = ? AND path = 'src/main.py'",
            (repo_id,),
        ).fetchall()
        assert sorted(tuple(row) for row in main_rows) == [(1, 0), (1, 0)]

        # README history: adds keep their paths; the pure rename is stored as
        # 0/0 on the new path; the deletion is 0/3 on the path that was removed.
        readme_rows = conn.execute(
            "SELECT path, added, removed FROM file_changes"
            " WHERE repo_id = ? AND path LIKE 'README%'",
            (repo_id,),
        ).fetchall()
        assert sorted(tuple(row) for row in readme_rows) == [
            ("README.md", 1, 0),
            ("README.md", 2, 0),
            ("README.rst", 0, 0),
            ("README.rst", 0, 3),
        ]

        # Binary files are excluded; empty commits have no file rows.
        n_blob = conn.execute(
            "SELECT COUNT(*) FROM file_changes WHERE repo_id = ? AND path = 'blob.bin'",
            (repo_id,),
        ).fetchone()[0]
        assert n_blob == 0
        n_empty_files = conn.execute(
            "SELECT COUNT(*) FROM file_changes WHERE repo_id = ? AND commit_hash = ?",
            (repo_id, hashes["c7"]),
        ).fetchone()[0]
        assert n_empty_files == 0

        # Author attribution: Bob made exactly c3, c4, c5 and c8.
        n_bob = conn.execute(
            "SELECT COUNT(*) FROM commits WHERE repo_id = ? AND author_email = ?",
            (repo_id, "bob@example.com"),
        ).fetchone()[0]
        assert n_bob == 4

    # Re-analysis replaces the old rows instead of duplicating them.
    analyse_repo(repo_id, repo_path)
    with db.connection() as conn:
        n_commits = conn.execute(
            "SELECT COUNT(*) FROM commits WHERE repo_id = ?", (repo_id,)
        ).fetchone()[0]
        n_files = conn.execute(
            "SELECT COUNT(*) FROM file_changes WHERE repo_id = ?", (repo_id,)
        ).fetchone()[0]
    assert (n_commits, n_files) == (8, 7)


def test_ancestors():
    """Directory rollup paths: every directory above the file, ending at ''."""
    assert ancestors("src/app.py") == ["src", ""]
    assert ancestors("a/b/c.txt") == ["a/b", "a", ""]
    assert ancestors("top.txt") == [""]
