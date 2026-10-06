"""HTTP endpoints that expose the stored metrics.

All endpoints share the same filter vocabulary (query parameters):
`from` / `to` (timestamps), `author`, `as_of` (reference commit), and
`commits` (comma-separated manual commit list). The POST commit-set
endpoint takes the same filters as a JSON body instead, so picked
commits can be sent as a proper list.
"""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import db
from ..analysis import queries
from ..models import (
    AuthorsOut,
    CommitsOut,
    CommitSetRequest,
    HistoryOut,
    ObjectMetricsOut,
)

router = APIRouter(prefix="/api/repos", tags=["metrics"])


def _require_repo(repo_id: int) -> dict:
    repo = db.get_repo(repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail=f"Repository {repo_id} not found")
    return repo


def _parse(value: Optional[str], label: str) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return queries.parse_ts(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"Invalid {label} timestamp: {value!r}"
        ) from exc


def _filters(
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    author: Optional[str] = Query(None),
    as_of: Optional[str] = Query(None),
    commits: Optional[str] = Query(None),
) -> queries.Filters:
    """Shared query-parameter filters for the GET endpoints."""
    hashes = [h.strip() for h in commits.split(",") if h.strip()] if commits else None
    return queries.Filters(
        author=author or None,
        from_ts=_parse(from_, "from"),
        to_ts=_parse(to, "to"),
        as_of=as_of or None,
        hashes=hashes,
    )


def _guarded(fn) -> dict:
    """Run a query, translating domain errors into HTTP responses."""
    try:
        return fn()
    except queries.UnknownCommit as exc:
        raise HTTPException(status_code=404, detail=f"Unknown commit: {exc}") from exc
    except queries.UnknownObject as exc:
        raise HTTPException(status_code=404, detail=f"Unknown object: {exc}") from exc


@router.get("/{repo_id}/metrics/object", response_model=ObjectMetricsOut)
def get_object_metrics(
    repo_id: int,
    kind: Literal["file", "dir"] = "dir",
    path: str = "",
    filters: queries.Filters = Depends(_filters),
) -> dict:
    """Metrics for one object: a file, a directory, or the repo root (path="")."""
    _require_repo(repo_id)
    return _guarded(lambda: queries.object_metrics(repo_id, kind, path, filters))


@router.get("/{repo_id}/metrics/history", response_model=HistoryOut)
def get_object_history(
    repo_id: int,
    kind: Literal["file", "dir"] = "dir",
    path: str = "",
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    filters: queries.Filters = Depends(_filters),
) -> dict:
    """Per-commit history of one object, newest first."""
    _require_repo(repo_id)
    return _guarded(
        lambda: queries.object_history(repo_id, kind, path, filters, limit, offset)
    )


@router.post("/{repo_id}/metrics/commit-set", response_model=ObjectMetricsOut)
def get_commit_set_metrics(repo_id: int, request: CommitSetRequest) -> dict:
    """Same metrics, but with the commit set (and filters) in a JSON body."""
    _require_repo(repo_id)
    filters = queries.Filters(
        author=request.author or None,
        from_ts=_parse(str(request.from_) if request.from_ is not None else None, "from"),
        to_ts=_parse(str(request.to) if request.to is not None else None, "to"),
        as_of=request.as_of or None,
        hashes=request.hashes or None,
    )
    return _guarded(
        lambda: queries.object_metrics(repo_id, request.kind, request.path, filters)
    )


@router.get("/{repo_id}/commits", response_model=CommitsOut)
def get_commits(
    repo_id: int,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    """All measured (non-merge) commits, newest first."""
    _require_repo(repo_id)
    return queries.list_commits(repo_id, limit, offset)


@router.get("/{repo_id}/authors", response_model=AuthorsOut)
def get_authors(repo_id: int, limit: int = Query(1000, ge=1, le=5000)) -> dict:
    """All authors with their totals over the whole history."""
    _require_repo(repo_id)
    return queries.list_authors(repo_id, limit)
