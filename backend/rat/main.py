"""The FastAPI application: entry point for the whole backend.

Run it with:  uvicorn rat.main:app --reload --port 8000
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import db
from .api import authors, metrics, repos


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Prepare the database before the server starts serving requests."""
    db.init_db()
    yield


app = FastAPI(title="Repo Analysis Tool (RAT)", version="0.1.0", lifespan=lifespan)

# The dashboard (a separate dev server) will call this API from another origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(repos.router)
app.include_router(metrics.router)
app.include_router(authors.router)


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    """Cheap endpoint to check that the server is alive."""
    return {"status": "ok"}


# Serve the built React dashboard (frontend/dist) when it exists, so the
# whole tool runs from this single server. Rebuild it with:
#   cd frontend && npm install && npm run build
_dashboard = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if (_dashboard / "index.html").is_file():
    app.mount("/", StaticFiles(directory=_dashboard, html=True), name="dashboard")
else:

    @app.get("/", tags=["meta"])
    def root() -> dict:
        """Friendly landing response until the dashboard is built."""
        return {
            "name": "Repo Analysis Tool",
            "docs": "/docs",
            "health": "/api/health",
            "dashboard": "not built yet - run: cd frontend && npm install && npm run build",
        }
