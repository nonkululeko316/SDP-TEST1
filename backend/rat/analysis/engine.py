"""Orchestrates one full analysis run for a repository."""
import time
from pathlib import Path

from .. import db
from .gitlog import stream_commits
from .store import MetricsWriter


def wipe_repo_metrics(repo_id: int) -> None:
    """Remove all previously stored metrics for a repository (re-run safe)."""
    with db.connection() as conn:
        conn.execute("DELETE FROM commits WHERE repo_id = ?", (repo_id,))
        conn.execute("DELETE FROM file_changes WHERE repo_id = ?", (repo_id,))
        conn.execute("DELETE FROM dir_changes WHERE repo_id = ?", (repo_id,))


def analyse_repo(repo_id: int, repo_root: Path) -> dict:
    """Analyse every non-merge commit reachable from HEAD in one pass."""
    started = time.time()
    wipe_repo_metrics(repo_id)
    writer = MetricsWriter(repo_id)
    for commit in stream_commits(repo_root):
        writer.add(commit)
    writer.flush()

    seconds = time.time() - started
    db.update_repo(
        repo_id,
        message=f"{writer.n_commits} commits, {writer.n_file_rows} file changes in {seconds:.1f}s",
    )
    return {"commits": writer.n_commits, "file_changes": writer.n_file_rows, "seconds": seconds}
