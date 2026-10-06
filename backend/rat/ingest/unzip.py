"""Turn an uploaded .zip file into a real git repository on disk."""
import shutil
import zipfile
from pathlib import Path


class IngestError(Exception):
    """Raised when an upload or clone cannot be turned into a git repository."""


def _safe_extract(zf: zipfile.ZipFile, dest: Path) -> None:
    """Extract the archive, refusing absolute paths and '..' escapes."""
    for member in zf.infolist():
        member_path = Path(member.filename)
        if member_path.is_absolute() or ".." in member_path.parts:
            raise IngestError(f"Unsafe path inside zip: {member.filename}")
    zf.extractall(dest)


def find_repo_root(folder: Path) -> Path | None:
    """Return the folder that directly contains .git (handles nested zips)."""
    if (folder / ".git").exists():
        return folder
    candidates = [p for p in folder.iterdir() if p.is_dir() and (p / ".git").exists()]
    return candidates[0] if len(candidates) == 1 else None


def ingest_zip(zip_path: Path, dest_dir: Path) -> Path:
    """Extract the upload and return the repository root path."""
    if not zipfile.is_zipfile(zip_path):
        raise IngestError("Uploaded file is not a valid zip archive")

    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True)

    with zipfile.ZipFile(zip_path) as zf:
        _safe_extract(zf, dest_dir)

    zip_path.unlink(missing_ok=True)

    root = find_repo_root(dest_dir)
    if root is None:
        raise IngestError("No .git directory or file found inside the zip")
    return root
