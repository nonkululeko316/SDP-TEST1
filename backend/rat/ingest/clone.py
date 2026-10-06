"""Turn a remote URL into a full local copy of the repository."""
import subprocess
from pathlib import Path

from .unzip import IngestError


def ingest_clone(url: str, dest_dir: Path) -> Path:
    """Deep (full-history) clone of `url` into `dest_dir`."""
    if not url.startswith(("http://", "https://", "git@", "ssh://")):
        raise IngestError(f"Unsupported URL: {url!r} (use https:// or ssh)")

    dest_dir.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["git", "clone", "--progress", url, str(dest_dir)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        tail = "\n".join(result.stderr.strip().splitlines()[-5:])
        raise IngestError(f"git clone failed: {tail}")
    return dest_dir
