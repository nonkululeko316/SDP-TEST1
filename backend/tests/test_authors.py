"""End-to-end tests of author merging (spec items 46, 47; item 36).

Two mechanisms are covered:

- **manual merges** - the /author-merges CRUD endpoints, their effect on
  /authors and /metrics, and their survival across re-analysis;
- **.mailmap** - written into the repo working tree, applied automatically
  by the next analysis.

The scenario repo has exactly two identities: 4 commits from
alice@example.com and 4 from bob@example.com (8 measured commits, +8/-3).
"""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from rat import db
from rat.analysis.engine import analyse_repo
from rat.main import app
from repo_builder import build_repo


@pytest.fixture()
def api(rat_env):
    """Analysed scenario repo + a TestClient bound to it."""
    build_repo(rat_env)
    repo_id = db.create_repo(name="sample", source_type="zip", source_ref="sample.zip")["id"]
    analyse_repo(repo_id, rat_env / "sample")
    return SimpleNamespace(client=TestClient(app), repo_id=repo_id, rat_env=rat_env)


def authors_url(api) -> str:
    return f"/api/repos/{api.repo_id}/authors"


def merges_url(api) -> str:
    return f"/api/repos/{api.repo_id}/author-merges"


def metrics_url(api) -> str:
    return f"/api/repos/{api.repo_id}/metrics/object"


def test_manual_merge_lifecycle(api):
    # Baseline: two separate identities, 4 commits each.
    body = api.client.get(authors_url(api)).json()
    assert body["total"] == 2
    assert {item["email"] for item in body["items"]} == {"alice@example.com", "bob@example.com"}
    assert all(item["identities"] == [] for item in body["items"])

    # Merge bob into alice.
    response = api.client.post(
        merges_url(api),
        json={"source_email": "bob@example.com", "target_email": "alice@example.com"},
    )
    assert response.status_code == 201
    merge = response.json()
    assert merge["repo_id"] == api.repo_id
    assert (merge["source_email"], merge["target_email"]) == ("bob@example.com", "alice@example.com")

    # One identity now, owning all 8 commits; the raw email is listed.
    body = api.client.get(authors_url(api)).json()
    assert body["total"] == 1
    (alice,) = body["items"]
    assert alice["email"] == "alice@example.com"
    assert (alice["commits"], alice["added"], alice["removed"]) == (8, 8, 3)
    assert alice["identities"] == ["bob@example.com"]

    assert api.client.get(merges_url(api)).json()["total"] == 1

    # Filtering by the merged-away email still finds bob's 4 commits (raw
    # identity match); the surviving email now finds all 8.
    response = api.client.get(metrics_url(api), params={"author": "bob@example.com"})
    assert response.json()["set"]["commit_count"] == 4
    response = api.client.get(metrics_url(api), params={"author": "alice@example.com"})
    assert response.json()["set"]["commit_count"] == 8

    # The same source cannot be merged twice.
    response = api.client.post(
        merges_url(api),
        json={"source_email": "bob@example.com", "target_email": "alice@example.com"},
    )
    assert response.status_code == 409

    # Re-analysis keeps manual merges (they are user configuration).
    analyse_repo(api.repo_id, api.rat_env / "sample")
    assert api.client.get(merges_url(api)).json()["total"] == 1
    body = api.client.get(authors_url(api)).json()
    assert body["total"] == 1
    assert body["items"][0]["identities"] == ["bob@example.com"]

    # Deleting the merge separates the identities again.
    response = api.client.delete(f"{merges_url(api)}/{merge['id']}")
    assert response.status_code == 204
    body = api.client.get(authors_url(api)).json()
    assert body["total"] == 2
    assert all(item["identities"] == [] for item in body["items"])

    # Deleting a gone merge, self-merge, and unknown emails are rejected.
    assert api.client.delete(f"{merges_url(api)}/{merge['id']}").status_code == 404
    response = api.client.post(
        merges_url(api),
        json={"source_email": "alice@example.com", "target_email": "alice@example.com"},
    )
    assert response.status_code == 400
    response = api.client.post(
        merges_url(api),
        json={"source_email": "  ", "target_email": "alice@example.com"},
    )
    assert response.status_code == 400
    response = api.client.post(
        merges_url(api),
        json={"source_email": "ghost@example.com", "target_email": "alice@example.com"},
    )
    assert response.status_code == 404
    response = api.client.post(
        merges_url(api),
        json={"source_email": "bob@example.com", "target_email": "ghost@example.com"},
    )
    assert response.status_code == 404


def test_mailmap_respected(api):
    """A repo .mailmap merges identities automatically at analysis time."""
    (api.rat_env / "sample" / ".mailmap").write_text(
        "Alice <alice@example.com> <bob@example.com>\n"
    )
    analyse_repo(api.repo_id, api.rat_env / "sample")

    body = api.client.get(authors_url(api)).json()
    assert body["total"] == 1
    (alice,) = body["items"]
    assert alice["email"] == "alice@example.com"
    assert alice["name"] == "Alice"
    assert (alice["commits"], alice["added"], alice["removed"]) == (8, 8, 3)
    assert alice["identities"] == ["bob@example.com"]

    # Raw identities stay stored, so the legacy email still filters.
    response = api.client.get(metrics_url(api), params={"author": "bob@example.com"})
    assert response.json()["set"]["commit_count"] == 4

    with db.connection() as conn:
        raws = {
            (row[0], row[1])
            for row in conn.execute(
                "SELECT DISTINCT raw_author_name, raw_author_email FROM commits"
                " WHERE repo_id = ? AND raw_author_email != author_email",
                (api.repo_id,),
            )
        }
        resolved = {
            (row[0], row[1])
            for row in conn.execute(
                "SELECT DISTINCT author_name, author_email FROM commits WHERE repo_id = ?",
                (api.repo_id,),
            )
        }
    assert raws == {("Bob", "bob@example.com")}
    assert resolved == {("Alice", "alice@example.com")}
