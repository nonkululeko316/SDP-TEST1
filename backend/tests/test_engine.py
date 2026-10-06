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
from rat import db
from rat.analysis.engine import analyse_repo
from rat.analysis.store import ancestors
from repo_builder import build_repo, git


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

        # The full ancestry graph is stored too (merge commits included),
        # so "as of commit X" walks never stop at a merge.
        n_graph = conn.execute(
            "SELECT COUNT(*) FROM commit_graph WHERE repo_id = ?", (repo_id,)
        ).fetchone()[0]
        assert n_graph == 9
        merge_parents = conn.execute(
            "SELECT parents FROM commit_graph WHERE repo_id = ? AND hash = ?",
            (repo_id, hashes["merge"]),
        ).fetchone()[0]
        assert sorted(merge_parents.split()) == sorted([hashes["c7"], hashes["c8"]])
        root_parents = conn.execute(
            "SELECT parents FROM commit_graph WHERE repo_id = ? AND hash = ?",
            (repo_id, hashes["c1"]),
        ).fetchone()[0]
        assert root_parents == ""

    # Re-analysis replaces the old rows instead of duplicating them.
    analyse_repo(repo_id, repo_path)
    with db.connection() as conn:
        n_commits = conn.execute(
            "SELECT COUNT(*) FROM commits WHERE repo_id = ?", (repo_id,)
        ).fetchone()[0]
        n_files = conn.execute(
            "SELECT COUNT(*) FROM file_changes WHERE repo_id = ?", (repo_id,)
        ).fetchone()[0]
        n_graph = conn.execute(
            "SELECT COUNT(*) FROM commit_graph WHERE repo_id = ?", (repo_id,)
        ).fetchone()[0]
    assert (n_commits, n_files, n_graph) == (8, 7, 9)


def test_ancestors():
    """Directory rollup paths: every directory above the file, ending at ''."""
    assert ancestors("src/app.py") == ["src", ""]
    assert ancestors("a/b/c.txt") == ["a/b", "a", ""]
    assert ancestors("top.txt") == [""]
