"""Pydantic models: the JSON shapes the API returns and accepts."""
from pydantic import BaseModel


class RepoOut(BaseModel):
    """One repository row, as returned by the API."""

    id: int
    name: str
    source_type: str    # "zip" or "url"
    source_ref: str     # original filename or URL
    local_path: str | None
    status: str         # queued | ingesting | ingested | error
    message: str
    created_at: str


class CloneRequest(BaseModel):
    """Body of POST /api/repos/clone."""

    url: str
    name: str | None = None
