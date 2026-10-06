"""HTTP endpoints for manual author merging (spec item 47).

The mailmap side of author merging is automatic: it is read from the
repository at analysis time. This module manages the manual overrides:

- GET    /api/repos/{id}/author-merges          list existing merges
- POST   /api/repos/{id}/author-merges          merge one identity into another
- DELETE /api/repos/{id}/author-merges/{mid}    undo a merge

Every change re-materialises the resolved author columns immediately, so
`/authors` and all metrics reflect the new identities at once.
"""
from pathlib import Path

from fastapi import APIRouter, HTTPException

from .. import db
from ..analysis import mailmap
from ..models import AuthorMergeOut, AuthorMergeRequest, AuthorMergesOut

router = APIRouter(prefix="/api/repos", tags=["authors"])


def _require_repo(repo_id: int) -> dict:
    repo = db.get_repo(repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail=f"Repository {repo_id} not found")
    return repo


def _repo_root(repo: dict):
    local_path = repo["local_path"]
    return Path(local_path) if local_path else None


def _current_emails(repo_id: int, root) -> set[str]:
    """The resolved emails currently visible as authors."""
    mapping = mailmap.resolve_map(repo_id, root)
    return {final_email for _, final_email in mapping.values()}


@router.get("/{repo_id}/author-merges", response_model=AuthorMergesOut)
def list_author_merges(repo_id: int) -> dict:
    """All manual merges defined for a repository."""
    _require_repo(repo_id)
    items = mailmap.list_merges(repo_id)
    return {"repo_id": repo_id, "total": len(items), "items": items}


@router.post("/{repo_id}/author-merges", response_model=AuthorMergeOut, status_code=201)
def create_author_merge(repo_id: int, request: AuthorMergeRequest) -> dict:
    """Merge `source_email` into `target_email` (both currently visible)."""
    repo = _require_repo(repo_id)
    source = request.source_email.strip()
    target = request.target_email.strip()
    if not source or not target:
        raise HTTPException(status_code=400, detail="source_email and target_email are required")
    if source == target:
        raise HTTPException(status_code=400, detail="source_email and target_email are the same")

    root = _repo_root(repo)
    if any(merge["source_email"] == source for merge in mailmap.list_merges(repo_id)):
        raise HTTPException(
            status_code=409,
            detail=f"Author {source} is already merged (delete that merge first)",
        )
    emails = _current_emails(repo_id, root)
    for candidate in (source, target):
        if candidate not in emails:
            raise HTTPException(status_code=404, detail=f"Unknown author: {candidate}")

    merge = mailmap.add_merge(repo_id, source, target)
    mailmap.resolve_authors(repo_id, root)
    return merge


@router.delete("/{repo_id}/author-merges/{merge_id}", status_code=204)
def delete_author_merge(repo_id: int, merge_id: int) -> None:
    """Undo a manual merge; the identities separate again."""
    repo = _require_repo(repo_id)
    if not mailmap.remove_merge(repo_id, merge_id):
        raise HTTPException(status_code=404, detail=f"Author merge {merge_id} not found")
    mailmap.resolve_authors(repo_id, _repo_root(repo))
