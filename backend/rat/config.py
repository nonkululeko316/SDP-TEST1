"""Where the RAT keeps its files on disk."""
import os
from pathlib import Path

# Layout: <project root>/backend/rat/config.py -> parents[2] is the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Everything the app writes (clones, uploads, database) lives under data/.
DATA_DIR = Path(os.environ.get("RAT_DATA_DIR", str(PROJECT_ROOT / "data")))
REPOS_DIR = DATA_DIR / "repos"   # one folder per repository
TMP_DIR = DATA_DIR / "tmp"       # temporary uploads before extraction
DB_PATH = DATA_DIR / "rat.db"    # the repository registry


def ensure_dirs() -> None:
    """Create the data folders if they are missing."""
    for folder in (DATA_DIR, REPOS_DIR, TMP_DIR):
        folder.mkdir(parents=True, exist_ok=True)
