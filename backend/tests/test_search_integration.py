"""Real Elasticsearch tests with explicitly Mock records and isolated test aliases."""

import json
import uuid
import re

from elasticsearch import Elasticsearch
from fastapi.testclient import TestClient
import pytest

from backend.app import create_app
from backend.config import Settings
from backend.import_jsonl import import_records, load_jsonl, publish_alias

pytestmark = pytest.mark.integration


def test_title_highlight_noise_and_full_author_metadata(tmp_path):
    client = Elasticsearch("http://127.0.0.1:9200", request_timeout=10)
    alias = f"scholarlens-test-{uuid.uuid4().hex[:8]}-mock"
    title = "Simulating the Dynamics of the Dancing Lights"
    authors = ["Mock First Author", "Mock Second Author", "Mock Third Author", "Mock Last Researcher"]
    source = tmp_path / "highlight.jsonl"
    source.write_text(json.dumps({"paper_id": "mock-highlight", "title": title, "authors": authors,
        "affiliation": ["University of Testing"], "fulltext": "The dynamics of the aurora are simulated."}), encoding="utf-8")
    try:
        records, meta = load_jsonl(source, "mock")
        import_records(client, alias, records, meta)
        with TestClient(create_app(Settings(index=alias), client)) as api:
            response = api.get("/api/search", params={"q": title})
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["total"] == 1
            hit = body["results"][0]
            assert hit["score"] > 0 and hit["authors"] == authors
            highlights = hit["highlights"]
            assert "affiliation" not in highlights
            marked = re.findall(r"<em>(.*?)</em>", str(highlights))
            assert any("dynamics" in value.lower() for value in marked)
            assert not any(value.lower() in {"the", "of"} for value in marked)
            assert re.sub(r"</?em>", "", highlights["title"][0]) == title
            author_hit = api.get("/api/search", params={"q": "Researcher", "field": "authors"}).json()["results"][0]
            assert author_hit["authors"] == authors
            assert author_hit["highlights"]["authors"] == ["Mock Last <em>Researcher</em>"]
            common = api.get("/api/search", params={"q": "of the", "field": "title"}).json()
            assert common["total"] == 1 and "<em>" in str(common["results"][0]["highlights"])
            phrase = api.get("/api/search", params={"q": title, "phrase": True}).json()
            assert phrase["total"] == 1 and "<em>" in str(phrase["results"][0]["highlights"])
    finally:
        for name in client.indices.get(index=f"{alias}-*", allow_no_indices=True):
            client.indices.delete(index=name)
        client.close()


@pytest.fixture(scope="module")
def environment(tmp_path_factory):
    client = Elasticsearch("http://127.0.0.1:9200", request_timeout=10)
    # Fail explicitly when the dependency is absent; never substitute a fake search engine.
    assert client.info()["version"]["number"] == "8.19.23"
    alias = f"scholarlens-test-{uuid.uuid4().hex[:8]}-mock"
    path = tmp_path_factory.mktemp("mock") / "papers.jsonl"
    rows = [
        {
            "paper_id": "mock-rank-a",
            "title": "Mock quasar quasar quasar",
            "authors": ["Ada Lovelace"],
            "date": "2024-01-15",
            "year": 2024,
            "affiliation": ["Lunar University"],
            "address": ["Oxford England"],
            "fulltext": "neutrino quantum telescope",
            "abstract": "Mock abstract",
        },
        {
            "paper_id": "mock-rank-b",
            "title": "Mock quasar with many unrelated words to dilute relevance",
            "authors": ["Grace Hopper"],
            "date": "2023-02-16",
            "year": 2023,
            "affiliation": ["Solar Institute"],
            "address": ["Paris France"],
            "fulltext": "neutrino orbit",
            "parse_status": "partial",
        },
        {"paper_id": "mock-empty", "title": "Mock quasar", "fulltext": "Mock missing metadata"},
        {
            "paper_id": "mock-html",
            "title": "Mock <script>alert(1)</script> quasar",
            "fulltext": "Mock text",
        },
        {
            "paper_id": "mock-broken",
            "title": "Mock quarantined",
            "fulltext": "garbled \ufffd quasar",
            "parse_status": "partial",
        },
        {"paper_id": "mock-rejected", "parse_status": "error"},
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    records, meta = load_jsonl(path, "mock")
    report = import_records(client, alias, records, meta)
    with TestClient(create_app(Settings(index=alias), client)) as api:
        yield api, client, alias, records, meta, report
    # Delete only this fixture's uniquely named resources.
    for name in client.indices.get(index=f"{alias}-*"):
        client.indices.delete(index=name)
    client.close()


@pytest.mark.parametrize(
    "field,queries",
    [
        ("title", ["quasar", "unrelated"]),
        ("authors", ["Ada", "Hopper"]),
        ("date", ["2024", "2023-02-16"]),
        ("affiliation", ["Lunar", "Solar"]),
        ("address", ["Oxford", "Paris"]),
        ("fulltext", ["quantum", "orbit"]),
    ],
)
def test_all_six_fields(environment, field, queries):
    api, *_ = environment
    for q in queries:
        response = api.get("/api/search", params={"q": q, "field": field})
        assert response.status_code == 200, response.text
        assert response.headers["X-ScholarLens-Data-Status"] == "mock"
        body = response.json()
        assert body["total"] > 0
        assert field in body["results"][0]["matched_fields"]
        assert body["results"][0]["score"] > 0
        assert "<em>" in str(body["results"][0]["highlights"])


def test_bm25_pagination_sort_filter_and_empty(environment):
    api, *_ = environment
    body = api.get("/api/search", params={"q": "quasar", "field": "title"}).json()
    assert body["results"][0]["paper_id"] == "mock-rank-a"
    scores = [r["score"] for r in body["results"]]
    assert scores == sorted(scores, reverse=True)
    first = api.get("/api/search", params={"q": "quasar", "page_size": 1}).json()
    second = api.get("/api/search", params={"q": "quasar", "page_size": 1, "page": 2}).json()
    assert first["results"][0]["paper_id"] != second["results"][0]["paper_id"]
    filtered = api.get("/api/search", params={"q": "quasar", "year_from": 2024}).json()
    assert [r["paper_id"] for r in filtered["results"]] == ["mock-rank-a"]
    for order, years in [("year_desc", [2024, 2023]), ("year_asc", [2023, 2024])]:
        sorted_body = api.get("/api/search", params={"q": "quasar", "sort": order}).json()
        assert [r["year"] for r in sorted_body["results"][:2]] == years
        assert all(r["year"] is None for r in sorted_body["results"][2:])
    empty = api.get("/api/search", params={"q": "notpresentanywhere"}).json()
    assert empty["total"] == 0 and empty["results"] == []


def test_phrase_fuzzy_html_and_quarantine(environment):
    api, *_ = environment
    assert (
        api.get("/api/search", params={"q": "quantum telescope", "phrase": True}).json()["total"]
        == 1
    )
    assert api.get("/api/search", params={"q": "quasra", "fuzzy": True}).json()["total"] > 0
    body = api.get("/api/search", params={"q": "quasar", "field": "title"}).json()
    html = next(r for r in body["results"] if r["paper_id"] == "mock-html")
    assert "&lt;script&gt;" in str(html["highlights"]) and "<script>" not in str(html["highlights"])
    assert api.get("/api/search", params={"q": "garbled", "field": "fulltext"}).json()["total"] == 0


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"q": " "},
        {"q": "x", "field": "abstract"},
        {"q": "x", "page": 0},
        {"q": "x", "page_size": 101},
        {"q": "x", "page": "oops"},
        {"q": "x", "year_from": 2025, "year_to": 2024},
        {"q": "x", "phrase": True, "fuzzy": True},
        {"q": "x", "page": 501},
    ],
)
def test_contract_errors(environment, params):
    api, *_ = environment
    response = api.get("/api/search", params=params)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_parameter"


def test_stats_no_private_fields_and_unimplemented_mode(environment):
    api, *_ = environment
    stats = api.get("/api/stats").json()
    assert stats["status"] == "mock" and stats["papers"] == 6 and stats["indexed"] == 5
    assert stats["parser"] == {"success": 0, "partial": 2, "failed": 1, "unknown": 3}
    from backend.mapping import MAPPING_VERSION
    assert stats["index"]["mapping_version"] == MAPPING_VERSION
    body = api.get("/api/search", params={"q": "quasar"}).json()
    assert set(body) == {"query", "total", "page", "page_size", "took_ms", "results"}
    assert all("pdf_path" not in r and "fulltext" not in r for r in body["results"])
    assert api.get("/api/search", params={"q": "quasar", "mode": "semantic"}).status_code == 503


def test_reimport_alias_switch_and_rollback(environment):
    api, client, alias, records, meta, old = environment
    new = import_records(client, alias, records[:1], {**meta, "accepted_records": 1})
    assert new["previous_generations"] == [old["generation"]]
    assert client.count(index=alias)["count"] == 1
    publish_alias(client, alias, old["generation"], [new["generation"]])
    assert client.count(index=alias)["count"] == 5


def test_missing_index_is_503():
    client = Elasticsearch("http://127.0.0.1:9200")
    with TestClient(create_app(Settings(index="scholarlens-never-created-mock"), client)) as api:
        response = api.get("/api/stats")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "dependency_unavailable"
    client.close()


def test_real_bulk_failure_preserves_active_alias(environment):
    _, client, alias, records, meta, _ = environment
    before = list(client.indices.get_alias(name=alias))
    broken = [{**records[0], "unexpected_mapping_field": "Mock invalid mapping"}]
    with pytest.raises(ValueError, match="active alias preserved"):
        import_records(client, alias, broken, meta)
    assert list(client.indices.get_alias(name=alias)) == before
    assert client.count(index=alias)["count"] == 5


def test_all_terms_can_span_multiple_fields(environment):
    api, *_ = environment
    r = api.get("/api/search", params={"q": "quasar Lunar", "field": "all"})
    assert r.status_code == 200 and r.json()["total"] == 1
    hit = r.json()["results"][0]
    assert hit["paper_id"] == "mock-rank-a"
    assert {"title", "affiliation"} <= set(hit["matched_fields"])
    assert "<em>" in str(hit["highlights"])
    assert (
        api.get("/api/search", params={"q": "quasar Lunar", "field": "title"}).json()["total"] == 0
    )
    assert (
        api.get("/api/search", params={"q": "quasra Lunar", "field": "all", "fuzzy": True}).json()[
            "total"
        ]
        == 1
    )
    assert (
        api.get("/api/search", params={"q": "quasar Lunar", "field": "all", "phrase": True}).json()[
            "total"
        ]
        == 0
    )
