"""Persistence for per-commit metrics: bulk inserts and directory rollups.

Rows are the raw material for every metric in the spec:
- `commits`      one row per non-merge commit (metadata)
- `file_changes` one row per changed file per commit (added/removed lines)
- `dir_changes`  per directory per commit, aggregated over its whole subtree
- `commit_graph` full ancestry edges (merge commits included) for "as of" queries

All commit-set and author metrics are later computed by summing/filtering
these rows in SQL, so no recomputation happens at query time.
"""
from ..db import connection
from .gitlog import CommitDiff

BATCH_SIZE = 20_000


def ancestors(path: str) -> list[str]:
    """Directories containing `path`, deepest first, ending with the root ''."""
    parts = path.split("/")
    dirs = ["/".join(parts[:i]) for i in range(len(parts) - 1, 0, -1)]
    dirs.append("")
    return dirs


class MetricsWriter:
    """Accumulates diff rows and flushes them to SQLite in batches."""

    def __init__(self, repo_id: int):
        self.repo_id = repo_id
        self.n_commits = 0
        self.n_file_rows = 0
        self._commits: list[tuple] = []
        self._files: list[tuple] = []
        self._dirs: list[tuple] = []
        self._graph: list[tuple] = []

    def add(self, commit: CommitDiff) -> None:
        """Record one commit and roll its file changes up into directories."""
        self.n_commits += 1
        self._commits.append((
            self.repo_id, commit.hash, commit.parents,
            commit.author_name, commit.author_email, commit.committer_ts,
        ))

        by_path: dict[str, list[int]] = {}
        for path, added, removed in commit.files:
            acc = by_path.setdefault(path, [0, 0])
            acc[0] += added
            acc[1] += removed

        subtree: dict[str, list[int]] = {}
        for path, (added, removed) in by_path.items():
            self._files.append((self.repo_id, commit.hash, path, added, removed))
            self.n_file_rows += 1
            for directory in ancestors(path):
                acc = subtree.setdefault(directory, [0, 0])
                acc[0] += added
                acc[1] += removed
        for directory, (added, removed) in subtree.items():
            self._dirs.append((self.repo_id, commit.hash, directory, added, removed))

        if len(self._files) >= BATCH_SIZE:
            self.flush()

    def add_graph(self, hash_: str, parents: str) -> None:
        """Record one node of the full ancestry graph (merges included)."""
        self._graph.append((self.repo_id, hash_, parents))
        if len(self._graph) >= BATCH_SIZE:
            self.flush()

    def flush(self) -> None:
        """Write pending rows to the database and clear the buffers."""
        if not (self._commits or self._files or self._dirs or self._graph):
            return
        with connection() as conn:
            conn.executemany(
                "INSERT INTO commits"
                " (repo_id, hash, parents, author_name, author_email, committer_ts)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                self._commits,
            )
            conn.executemany(
                "INSERT INTO file_changes (repo_id, commit_hash, path, added, removed)"
                " VALUES (?, ?, ?, ?, ?)",
                self._files,
            )
            conn.executemany(
                "INSERT INTO dir_changes (repo_id, commit_hash, path, added, removed)"
                " VALUES (?, ?, ?, ?, ?)",
                self._dirs,
            )
            conn.executemany(
                "INSERT INTO commit_graph (repo_id, hash, parents) VALUES (?, ?, ?)",
                self._graph,
            )
        self._commits, self._files, self._dirs, self._graph = [], [], [], []
