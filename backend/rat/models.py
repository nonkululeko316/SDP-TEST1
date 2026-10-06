"""Pydantic models: the JSON shapes the API returns and accepts."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RepoOut(BaseModel):
    """One repository row, as returned by the API."""

    id: int
    name: str
    source_type: str    # "zip" or "url"
    source_ref: str     # original filename or URL
    local_path: str | None
    status: str         # queued | ingesting | analysing | ready | error
    message: str
    created_at: str


class CloneRequest(BaseModel):
    """Body of POST /api/repos/clone."""

    url: str
    name: str | None = None


class SetInfo(BaseModel):
    """Which commits were measured (|H| and the filters that selected them)."""

    commit_count: int
    from_ts: int | None = None           # inclusive lower bound (unix seconds)
    to_ts: int | None = None             # exclusive upper bound (unix seconds)
    author: str | None = None
    as_of: str | None = None
    hashes_requested: int | None = None
    hashes_missing: list[str] = []


class AuthorMetricsOut(BaseModel):
    """One author's contribution to one object over the selected commit set."""

    name: str
    email: str
    commits: int
    modifications: int
    added: int
    removed: int
    churn: int
    ownership: float


class ChildMetricsOut(BaseModel):
    """Immediate child (file or directory) of the queried directory."""

    kind: str                            # "file" | "dir"
    path: str
    added: int
    removed: int
    growth: int
    churn: int
    modifications: int


class ObjectMetricsOut(BaseModel):
    """All metrics for one object (file, directory, or repo via path="")."""

    repo_id: int
    kind: str
    path: str
    set: SetInfo
    added: int
    removed: int
    growth: int                          # delta = added - removed
    churn: int                           # lambda = added + removed
    modifications: int                   # n: commits in H with churn > 0
    modification_frequency: float        # eta = n / |H| (0 when H is empty)
    churn_rate: float                    # rho = churn / |H| (0 when H is empty)
    authors: list[AuthorMetricsOut]
    children: list[ChildMetricsOut] = []


class HistoryItemOut(BaseModel):
    """One commit's contribution to the queried object."""

    hash: str
    committer_ts: int
    author_name: str
    author_email: str
    added: int
    removed: int
    growth: int
    churn: int


class HistoryOut(BaseModel):
    """Per-commit history of one object (newest first)."""

    repo_id: int
    kind: str
    path: str
    total: int
    items: list[HistoryItemOut]


class CommitItemOut(BaseModel):
    """One commit (for the manual commit-set picker)."""

    hash: str
    committer_ts: int
    author_name: str
    author_email: str
    parents: str
    added: int
    removed: int
    files_changed: int


class CommitsOut(BaseModel):
    repo_id: int
    total: int
    items: list[CommitItemOut]


class AuthorItemOut(BaseModel):
    """One author row (for filter drop-downs and the author table)."""

    email: str
    name: str
    commits: int
    added: int
    removed: int
    first_ts: int
    last_ts: int
    identities: list[str] = []          # raw emails merged into this identity


class AuthorsOut(BaseModel):
    repo_id: int
    total: int
    items: list[AuthorItemOut]


class AuthorMergeRequest(BaseModel):
    """Body of POST /api/repos/{id}/author-merges."""

    source_email: str                   # identity that disappears
    target_email: str                   # identity it merges into


class AuthorMergeOut(BaseModel):
    """One manual author merge."""

    id: int
    repo_id: int
    source_email: str
    target_email: str
    created_at: str


class AuthorMergesOut(BaseModel):
    repo_id: int
    total: int
    items: list[AuthorMergeOut]


class CommitSetRequest(BaseModel):
    """Body of POST /api/repos/{id}/metrics/commit-set: a manual commit list."""

    model_config = ConfigDict(populate_by_name=True)

    hashes: list[str] = Field(default_factory=list)
    from_: str | int | None = Field(default=None, alias="from")
    to: str | int | None = None
    author: str | None = None
    as_of: str | None = None
    kind: Literal["file", "dir"] = "dir"
    path: str = ""
