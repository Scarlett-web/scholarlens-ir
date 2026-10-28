"""Discovery response contract with synthetic documents; no ES or user data."""

from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import discovery


@pytest.fixture
def client(monkeypatch):
    documents = [
        {"paper_id": "synthetic-org", "title": "Synthetic institution example",
         "authors": ["Fixture author"], "affiliation": ["Fixture university"],
         "year": 2026, "abstract": "Contract-only fixture.",
         "pdf_path": "/private/fixture.pdf", "errors": ["private diagnostic"]},
        {"paper_id": "synthetic-missing", "title": "Synthetic missing metadata",
         "authors": [], "year": None, "abstract": "No institution supplied.",
         "source_file": "/private/source.jsonl"},
    ]

    def project(source):
        return [{"_source": {key: deepcopy(value) for key, value in doc.items()
                              if key in source}} for doc in documents]

    class SearchFixture:
        def search(self, **params):
            return {"hits": {"total": {"value": 2},
                             "hits": project(params["source"])[:params["size"]]},
                    "aggregations": {"years": {"buckets": [
                        {"key": 2026, "doc_count": 1}]}}}

    monkeypatch.setattr(discovery, "scan", lambda es, **params: iter(project(params["source"])))
    app = FastAPI()
    app.include_router(discovery.router(SearchFixture(), lambda: ("fixture", {"data_status": "synthetic"})))
    with TestClient(app) as api:
        yield api


@pytest.mark.parametrize("route", ["/api/discover?limit=2", "/api/discover/random?limit=2&seed=fixture"])
def test_institutions_survive_summary_and_private_fields_are_absent(client, route):
    response = client.get(route)
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "synthetic"
    rows = {row["paper_id"]: row for row in payload["recommendations"]}
    assert rows["synthetic-org"]["affiliation"] == ["Fixture university"]
    assert rows["synthetic-missing"]["affiliation"] == []
    assert not any({"pdf_path", "source_file", "errors"}.intersection(row) for row in rows.values())


def test_random_exclusion_and_seed_remain_compatible(client):
    route = "/api/discover/random?limit=1&seed=fixture&exclude=synthetic-org"
    first = client.get(route).json()
    assert first == client.get(route).json()
    assert first["seed"] == "fixture" and first["excluded_count"] == 1
    assert [row["paper_id"] for row in first["recommendations"]] == ["synthetic-missing"]
