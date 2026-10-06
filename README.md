# Repo Analysis Tool (RAT)

A web-app dashboard that measures software metrics across multiple git repositories — per **file**, **directory**, **repository**, **commit set** and **author** — as specified by the COMS3011A test brief.

Built with a **FastAPI + SQLite** backend and a **React (Vite) + Recharts** frontend.

## Features

- **Repository ingestion** — two ways in:
  - Upload a `.zip` of a local clone (must contain the `.git` directory; GitHub's "Download ZIP" button strips it and is rejected).
  - Clone from a remote URL (full, non-shallow history).
- **Metric engine** — one streaming `git log` pass per repository into SQLite, honouring the spec rules:
  - Non-merge commits only.
  - Rename detection at 50% (`-M50%`), so pure renames contribute zero change.
  - Binary files excluded; deletions attributed to their original path.
  - Directory metrics roll up over every ancestor folder; repository metrics = root directory metrics.
  - Commit-set filtering uses **committer** dates, and every query can be pinned "as of" any commit.
- **Filtering** — by repository, author, file/directory, and commit set: a time range **or** a manually selected set of commits. All filters combine (AND).
- **Author merging** — two stages: `.mailmap` support (committed to the repo, re-read on re-analysis) plus **manual merges** with undo, managed from the dashboard. Raw author data is always preserved, and filters on either the old or merged email still work.
- **Multi-repository** — a registry page lists every repository with live status (`queued → ingesting → analysing → ready` / `error`) and per-repo dashboards.
- **Dashboard** — metric cards, clickable directory browser, per-child churn chart, cumulative growth/churn chart, author pie and churn/ownership charts, paginated commit history, and an author management tab.

Metrics are validated against ground truth on real repositories (e.g. cJSON `v1.7.18`: 955 non-merge commits, +46 377 / −11 211 lines — matches independent `git log` sums).

## Project layout

```
backend/
  rat/                  FastAPI app
    api/                routes: repos, metrics, authors
    analysis/           git log parser, metric store, mailmap/manual merge resolution
    ingest/             zip extraction + clone workers
    db.py, models.py    SQLite schema + Pydantic schemas
  tests/                pytest suite (engine + metrics API + author merging)
frontend/
  src/                  React app (pages, components, API client, styles)
data/                   runtime data (repos, SQLite DB) — created on first run
checklist.md            the 58-item requirements checklist this project follows
```

## Getting started

### Backend (port 8000)

```bash
cd /home/vmuser/Documents/SDP-TEST1          # repo root
python3 -m venv .venv                        # first time only
.venv/bin/pip install -r backend/requirements.txt

cd backend
../.venv/bin/python -m uvicorn rat.main:app --reload --port 8000
```

- Interactive API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/api/health

### Frontend

Two ways to run it:

**A. Dev server** (hot reload, port 5173, proxies `/api` to the backend):

```bash
cd frontend
npm install        # first time only
npm run dev        # open http://localhost:5173
```

**B. Single server** (build once, FastAPI serves the dashboard at `/`):

```bash
cd frontend
npm run build      # writes frontend/dist
# restart-free: with uvicorn --reload the backend picks it up automatically
# now http://localhost:8000/ serves the whole app
```

## Tests

```bash
cd backend
../.venv/bin/python -m pytest -q      # 17 tests: ingestion pipeline, metric engine, metrics API, author merging
```

The suite builds miniature git repositories on the fly and asserts exact metric totals, filter behaviour, `.mailmap` resolution and manual merge lifecycle.

## API overview

| Method | Path | Purpose |
| ------ | ---- | ------- |
| GET  | `/api/repos` | list repositories (registry) |
| POST | `/api/repos/upload` | ingest a `.zip` upload (multipart field `file`) |
| POST | `/api/repos/clone` | clone + ingest from a remote URL |
| POST | `/api/repos/{id}/analyse` | (re-)run analysis, 202 |
| GET  | `/api/repos/{id}/metrics/object` | metrics for a file, directory or the repo |
| POST | `/api/repos/{id}/metrics/commit-set` | metrics over a filtered commit set (time range / manual hashes) |
| GET  | `/api/repos/{id}/metrics/history` | per-commit history for an object, paginated |
| GET  | `/api/repos/{id}/commits` | list commits (for the manual commit picker) |
| GET  | `/api/repos/{id}/authors` | resolved authors with identity aliases |
| GET/POST/DELETE | `/api/repos/{id}/author-merges` | manual author merges (create / list / undo) |

Every metrics query accepts the combined filters `author`, `from`, `to` (committer dates) and `as_of` (commit hash), and all metrics are computed on non-merge commits with 50% rename detection and binaries excluded.
