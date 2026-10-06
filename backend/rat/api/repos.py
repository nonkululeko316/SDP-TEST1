"""HTTP endpoints for adding and listing repositories."""
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from .. import config, db
from ..ingest.clone import ingest_clone
from ..ingest.jobs import run_repo_job
from ..ingest.unzip import ingest_zip
from ..models import CloneRequest, RepoOut

router = APIRouter(prefix="/api/repos", tags=["repositories"])


def _repo_dir(repo_id: int) -> Path:
    """Folder on disk where repository `repo_id` lives."""
    return config.REPOS_DIR / str(repo_id)


def _require_repo(repo_id: int) -> dict:
    repo = db.get_repo(repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail=f"Repository {repo_id} not found")
    return repo


@router.get("", response_model=list[RepoOut])
def list_repositories() -> list[dict]:
    """All repositories known to the tool."""
    return db.list_repos()


@router.get("/{repo_id}", response_model=RepoOut)
def get_repository(repo_id: int) -> dict:
    """Detail of one repository, including ingestion status/message."""
    return _require_repo(repo_id)


@router.post("/upload", response_model=RepoOut, status_code=201)
async def upload_zip(file: UploadFile) -> dict:
    """Accept a .zip of a repo (must contain .git) and ingest it."""
    filename = Path(file.filename or "upload.zip").name
    if not filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Please upload a .zip file")

    repo = db.create_repo(name=Path(filename).stem, source_type="zip", source_ref=filename)
    repo_id = repo["id"]

    tmp_zip = config.TMP_DIR / f"{repo_id}.zip"
    try:
        with tmp_zip.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                out.write(chunk)
    except OSError as exc:
        db.update_repo(repo_id, status="error", message=f"Could not save upload: {exc}")
        raise HTTPException(status_code=500, detail="Could not save upload") from exc

    def task() -> None:
        root = ingest_zip(tmp_zip, _repo_dir(repo_id))
        db.update_repo(repo_id, local_path=str(root))

    run_repo_job(repo_id, task)
    return db.get_repo(repo_id)


@router.post("/clone", response_model=RepoOut, status_code=201)
def clone_repository(request: CloneRequest) -> dict:
    """Accept a remote URL and deeply clone it in the background."""
    url = request.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    default_name = Path(url.rstrip("/").rsplit("/", 1)[-1]).stem or "repo"
    repo = db.create_repo(name=request.name or default_name, source_type="url", source_ref=url)
    repo_id = repo["id"]

    def task() -> None:
        root = ingest_clone(url, _repo_dir(repo_id))
        db.update_repo(repo_id, local_path=str(root))

    run_repo_job(repo_id, task)
    return db.get_repo(repo_id)
