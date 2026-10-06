"""The FastAPI application: entry point for the whole backend.

Run it with:  uvicorn rat.main:app --reload --port 8000
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .api import metrics, repos


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


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    """Cheap endpoint to check that the server is alive."""
    return {"status": "ok"}


@app.get("/", tags=["meta"])
def root() -> dict:
    """Friendly landing response with links to the docs."""
    return {"name": "Repo Analysis Tool", "docs": "/docs", "health": "/api/health"}
