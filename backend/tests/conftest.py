"""Test fixtures: redirect all app data into a per-test temp directory."""
import pytest

from rat import config, db


@pytest.fixture()
def rat_env(tmp_path, monkeypatch):
    """A fresh data directory and database for every test."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "REPOS_DIR", tmp_path / "repos")
    monkeypatch.setattr(config, "TMP_DIR", tmp_path / "tmp")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "rat.db")
    db.init_db()
    yield tmp_path
