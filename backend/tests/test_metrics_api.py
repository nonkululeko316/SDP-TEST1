"""End-to-end tests of the metrics query API.

The scenario repository from repo_builder is analysed once per test, then
queried through the real FastAPI app (TestClient). All expected numbers
are hand-derived from the scenario timeline:

  root (all 8 commits):   +8 / -3, churn 11, modifications 5 (c1,c2,c3,c5,c8)
  date range Jan 5..7:    c5 (0/3), c6 (none), c7 (none)  -> +0 / -3
  as of c3:               c1 (5/0) + c2 (1/0) + c3 (1/0)  -> +7 / -0
  author bob:             c3 (1/0) + c4 (0/0) + c5 (0/3) + c8 (1/0) -> +2 / -3
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
    hashes = build_repo(rat_env)
    repo_id = db.create_repo(name="sample", source_type="zip", source_ref="sample.zip")["id"]
    analyse_repo(repo_id, rat_env / "sample")
    return SimpleNamespace(client=TestClient(app), repo_id=repo_id, hashes=hashes)


def object_url(api) -> str:
    return f"/api/repos/{api.repo_id}/metrics/object"


def test_root_metrics_and_children(api):
    response = api.client.get(object_url(api))
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "dir"
    assert body["path"] == ""

    assert body["set"]["commit_count"] == 8
    assert (body["added"], body["removed"]) == (8, 3)
    assert body["growth"] == 5
    assert body["churn"] == 11
    assert body["modifications"] == 5
    assert body["modification_frequency"] == 0.625
    assert body["churn_rate"] == 1.375

    children = {child["path"]: child for child in body["children"]}
    assert set(children) == {"README.md", "README.rst", "src"}
    assert children["README.md"] == {
        "kind": "file", "path": "README.md", "added": 3, "removed": 0,
        "growth": 3, "churn": 3, "modifications": 2,
    }
    assert (children["README.rst"]["churn"], children["README.rst"]["modifications"]) == (3, 1)
    assert children["src"]["kind"] == "dir"
    assert (children["src"]["added"], children["src"]["removed"]) == (5, 0)
    assert children["src"]["modifications"] == 3
    assert "blob.bin" not in children  # binary files are never measured

    authors = {author["email"]: author for author in body["authors"]}
    assert set(authors) == {"alice@example.com", "bob@example.com"}
    alice, bob = authors["alice@example.com"], authors["bob@example.com"]
    assert (alice["commits"], alice["modifications"]) == (4, 2)
    assert alice["churn"] == 6
    assert alice["ownership"] == 0.5455
    assert (bob["commits"], bob["modifications"]) == (4, 3)
    assert bob["churn"] == 5
    assert bob["ownership"] == 0.4545


def test_file_metrics(api):
    response = api.client.get(object_url(api), params={"kind": "file", "path": "README.rst"})
    assert response.status_code == 200
    body = response.json()
    assert (body["added"], body["removed"]) == (0, 3)
    assert body["growth"] == -3
    assert body["modifications"] == 1
    # c4 (the pure rename, 0/0) and c5 (the deletion) were both Bob's.
    assert len(body["authors"]) == 1
    assert body["authors"][0]["email"] == "bob@example.com"
    assert body["authors"][0]["modifications"] == 1
    assert body["authors"][0]["ownership"] == 1.0

    response = api.client.get(object_url(api), params={"kind": "file", "path": "src/app.py"})
    body = response.json()
    assert (body["added"], body["removed"]) == (3, 0)
    assert body["modifications"] == 1


def test_directory_metrics_and_children(api):
    response = api.client.get(object_url(api), params={"path": "src"})
    assert response.status_code == 200
    body = response.json()
    assert (body["added"], body["removed"]) == (5, 0)
    assert body["modifications"] == 3

    children = {child["path"]: child for child in body["children"]}
    assert set(children) == {"src/app.py", "src/main.py"}
    assert children["src/app.py"]["modifications"] == 1
    assert children["src/main.py"]["churn"] == 2
    assert children["src/main.py"]["modifications"] == 2


def test_author_filter(api):
    response = api.client.get(object_url(api), params={"author": "bob@example.com"})
    body = response.json()
    assert body["set"]["commit_count"] == 4
    assert (body["added"], body["removed"]) == (2, 3)
    assert body["growth"] == -1
    assert [author["email"] for author in body["authors"]] == ["bob@example.com"]


def test_date_range_filter(api):
    # from is inclusive, to is exclusive -> c5, c6, c7 (not c8 on Jan 8).
    response = api.client.get(object_url(api), params={"from": "2024-01-05", "to": "2024-01-08"})
    body = response.json()
    assert body["set"]["commit_count"] == 3
    assert (body["added"], body["removed"]) == (0, 3)


def test_as_of_commit(api):
    response = api.client.get(object_url(api), params={"as_of": api.hashes["c3"]})
    body = response.json()
    assert body["set"]["commit_count"] == 3
    assert (body["added"], body["removed"]) == (7, 0)

    # Ancestors of the merge = everything: the walk crosses merge commits.
    response = api.client.get(object_url(api), params={"as_of": api.hashes["merge"]})
    body = response.json()
    assert body["set"]["commit_count"] == 8
    assert (body["added"], body["removed"]) == (8, 3)


def test_manual_commit_set_get(api):
    commits = f"{api.hashes['c1']},{api.hashes['c5']}"
    response = api.client.get(object_url(api), params={"commits": commits})
    body = response.json()
    assert body["set"]["commit_count"] == 2
    assert (body["added"], body["removed"]) == (5, 3)


def test_commit_set_post(api):
    response = api.client.post(
        f"/api/repos/{api.repo_id}/metrics/commit-set",
        json={"hashes": [api.hashes["c3"], api.hashes["c8"]],
              "kind": "file", "path": "src/main.py"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["set"]["commit_count"] == 2
    assert (body["added"], body["removed"]) == (2, 0)

    # The body also accepts the same time/author filters ("from" alias).
    response = api.client.post(
        f"/api/repos/{api.repo_id}/metrics/commit-set",
        json={"from": "2024-01-05", "to": "2024-01-08"},
    )
    assert response.json()["set"]["commit_count"] == 3


def test_commit_set_post_reports_missing_hashes(api):
    response = api.client.post(
        f"/api/repos/{api.repo_id}/metrics/commit-set",
        json={"hashes": ["deadbeef"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["set"]["hashes_requested"] == 1
    assert body["set"]["hashes_missing"] == ["deadbeef"]
    assert body["set"]["commit_count"] == 0
    assert body["added"] == 0


def test_object_history(api):
    response = api.client.get(
        f"/api/repos/{api.repo_id}/metrics/history",
        params={"kind": "file", "path": "README.rst"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert [item["hash"] for item in body["items"]] == [api.hashes["c5"], api.hashes["c4"]]
    assert body["items"][0]["removed"] == 3
    assert body["items"][1]["churn"] == 0  # the pure rename


def test_commits_endpoint(api):
    response = api.client.get(f"/api/repos/{api.repo_id}/commits")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 8
    assert body["items"][0]["hash"] == api.hashes["c8"]

    by_hash = {item["hash"]: item for item in body["items"]}
    assert by_hash[api.hashes["c4"]]["files_changed"] == 1
    assert by_hash[api.hashes["c7"]]["files_changed"] == 0  # empty commit
    assert api.hashes["merge"] not in by_hash  # merges are never measured


def test_authors_endpoint(api):
    response = api.client.get(f"/api/repos/{api.repo_id}/authors")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    alice, bob = body["items"]
    assert alice["email"] == "alice@example.com"
    assert alice["added"] == 6
    assert bob["removed"] == 3


def test_error_paths(api):
    url = object_url(api)
    assert api.client.get(url, params={"kind": "file", "path": "nope.txt"}).status_code == 404
    assert api.client.get(url, params={"kind": "file", "path": "blob.bin"}).status_code == 404
    assert api.client.get(url, params={"from": "not-a-date"}).status_code == 400
    assert api.client.get(url, params={"kind": "banana"}).status_code == 422
    assert api.client.get(url, params={"as_of": "f" * 40}).status_code == 404
    assert api.client.get("/api/repos/999/metrics/object").status_code == 404
