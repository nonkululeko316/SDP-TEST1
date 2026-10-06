"""Run long tasks (extract, clone, analyse) in background threads.

The web server must stay responsive while a big repository is being
processed, so each ingestion runs on its own daemon thread and reports
progress through the repository row in the database.
"""
import threading
import traceback
from typing import Callable

from .. import db


def run_repo_job(
    repo_id: int,
    task: Callable[[], None],
    *,
    start_status: str = "ingesting",
    done_status: str = "ready",
) -> None:
    """Run `task` in the background; record success/failure on the repo row.

    The same machinery drives ingestion and re-analysis; the caller picks
    the start/done statuses. A successful run keeps the message written by
    the task (e.g. the analysis stats); a failure replaces it with the error.
    """

    def _runner() -> None:
        try:
            db.update_repo(repo_id, status=start_status, message="")
            task()
        except Exception as exc:  # noqa: BLE001 - surface any failure to the user
            traceback.print_exc()
            db.update_repo(repo_id, status="error", message=str(exc))
        else:
            db.update_repo(repo_id, status=done_status)

    threading.Thread(target=_runner, name=f"rat-job-{repo_id}", daemon=True).start()
