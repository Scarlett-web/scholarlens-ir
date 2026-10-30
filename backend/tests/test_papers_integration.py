"""Detail/PDF and frontend contract checks against isolated real ES indexes."""

import json
from pathlib import Path
from urllib.parse import quote
import uuid

from elasticsearch import Elasticsearch
from fastapi.testclient import TestClient
import pytest

from backend.app1 import create_app
from backend.config import Settings
from backend.import_jsonl import import_records, load_jsonl

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def papers_api(tmp_path_factory):
    client = Elasticsearch("http://127.0.0.1:9200", request_timeout=10)
    assert client.info()["version"]["number"] == "8.19.23"
    alias = f"scholarlens-test-details-{uuid.uuid4().hex[:8]}-mock"
    original = Path("data/sample/mock_papers.jsonl")
    rows = [json.loads(line) for line in original.read_text(encoding="utf-8-sig").splitlines()]
    rows.extend(
        [
            {"paper_id": "mock-stage2:empty", "parse_status": "partial", "pages": None},
            {
                "paper_id": "mock-stage2-pr",
                "title": "Mock parser schema",
                "authors": [],
                "date": "",
                "year": None,
                "affiliation": [],
                "address": [],
                "abstract": "",
                "fulltext": "Mock partial body",
                "parse_status": "partial",
                "pages": {"first": None, "last": None, "count": 9},
                "source_file": "paper.pdf",
                "pdf_path": "../oriPDFs.rar/oriPDFs/paper.pdf",
                "errors": ["missing: date", "private path C:/private/paper.pdf"],
            },
        ]
    )
    path = tmp_path_factory.mktemp("stage2") / "papers.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    records, meta = load_jsonl(path, "mock")
    report = import_records(client, alias, records, meta)
    try:
        with TestClient(create_app(Settings(index=alias), client)) as api:
            yield api, client, alias, report
    finally:
        for name in client.indices.get(index=f"{alias}-*"):
            client.indices.delete(index=name)
        client.close()


def test_detail_existing_mock_matches_original(papers_api):
    api, *_ = papers_api
    response = api.get("/api/papers/mock-0002")
    assert response.status_code == 200
    assert response.headers["X-ScholarLens-Data-Status"] == "mock"
    body = response.json()
    original = json.loads(
        Path("data/sample/mock_papers.jsonl").read_text(encoding="utf-8-sig").splitlines()[1]
    )
    for key in (
        "paper_id",
        "title",
        "authors",
        "date",
        "year",
        "affiliation",
        "address",
        "abstract",
        "fulltext",
        "pages",
    ):
        assert body[key] == original[key]
    assert body["pdf_available"] is False
    assert body["source_status"] == {"pdf": "pdf_not_available", "parse_status": "unknown"}
    assert body["chunks"] == body["available_actions"] == []
    assert not ({"pdf_path", "source_file", "errors", "date_value", "pdf_url"} & body.keys())


@pytest.mark.parametrize("paper_id", ["mock-0001", "mock-0002", "mock-stage2-pr"])
def test_pdf_not_delivered_is_json_404(papers_api, paper_id):
    api, *_ = papers_api
    response = api.get(f"/api/papers/{paper_id}/pdf")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {
        "error": {
            "code": "pdf_not_available",
            "message": "原始 PDF 尚未交付或暂不可访问",
            "details": {},
        }
    }


@pytest.mark.parametrize("suffix", ["", "/pdf"])
def test_paper_not_found_distinct_from_pdf_missing(papers_api, suffix):
    api, *_ = papers_api
    response = api.get("/api/papers/mock-never-existed" + suffix)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "paper_not_found"
    assert set(response.json()["error"]) == {"code", "message", "details"}


def test_empty_fields_and_pr_pages(papers_api):
    api, *_ = papers_api
    empty = api.get("/api/papers/" + quote("mock-stage2:empty", safe="")).json()
    assert empty["date"] == empty["title"] == empty["abstract"] == empty["fulltext"] == ""
    assert empty["authors"] == empty["affiliation"] == empty["address"] == []
    assert empty["year"] is empty["pages"] is None
    assert empty["source_status"]["parse_status"] == "partial"
    response = api.get("/api/papers/mock-stage2-pr")
    body = response.json()
    assert body["pages"] == {"first": None, "last": None, "count": 9}
    assert body["fulltext"] == "Mock partial body"
    assert "C:/private" not in response.text and "oriPDFs" not in response.text


@pytest.mark.parametrize("paper_id", [" ", " mock-0001", "x" * 513, "a/b", "a\\b", "bad\x01id"])
def test_invalid_id_is_400(papers_api, paper_id):
    api, *_ = papers_api
    response = api.get("/api/papers/" + quote(paper_id, safe=""))
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "invalid_parameter"


def test_search_frontend_shape(papers_api):
    api, *_ = papers_api
    params = {
        "q": "computer",
        "field": "title",
        "mode": "keyword",
        "page": 1,
        "page_size": 2,
        "sort": "relevance",
    }
    response = api.get("/api/search", params=params)
    body = response.json()
    assert response.status_code == 200
    assert body["total"] == 1 and body["page"] == 1 and body["page_size"] == 2
    assert body["query"] == {
        **params,
        "year_from": None,
        "year_to": None,
        "phrase": False,
        "fuzzy": False,
    }
    hit = body["results"][0]
    assert set(hit) == {
        "paper_id",
        "title",
        "authors",
        "year",
        "abstract_snippet",
        "highlights",
        "score",
        "matched_fields",
        "explanation",
    }
    assert hit["paper_id"] == "mock-0002" and hit["authors"] == ["Mock Author C"]
    assert isinstance(hit["score"], float) and hit["score"] > 0
    assert hit["matched_fields"] == ["title"]
    assert hit["highlights"]["title"] == ["Mock <em>Computer</em> Vision Survey"]
    empty = api.get("/api/search", params={"q": "notpresentanywhere"}).json()
    assert empty["results"] == [] and empty["total"] == 0


@pytest.mark.parametrize(
    "url,method,status,code",
    [
        ("/api/unknown-route", "get", 404, "not_found"),
        ("/api/stats", "post", 405, "method_not_allowed"),
        ("/api/search?page=oops&q=x", "get", 400, "invalid_parameter"),
        ("/api/search", "get", 400, "invalid_parameter"),
    ],
)
def test_uniform_errors(papers_api, url, method, status, code):
    api, *_ = papers_api
    response = getattr(api, method)(url)
    assert response.status_code == status
    assert set(response.json()) == {"error"}
    assert response.json()["error"]["code"] == code


def test_detail_missing_index_is_dependency_error():
    client = Elasticsearch("http://127.0.0.1:9200")
    try:
        with TestClient(create_app(Settings(index="scholarlens-no-details-mock"), client)) as api:
            response = api.get("/api/papers/mock-0001")
            assert response.status_code == 503
            assert response.json()["error"]["code"] == "dependency_unavailable"
    finally:
        client.close()


def test_openapi_documents_public_shapes(papers_api):
    api, *_ = papers_api
    spec = api.get("/openapi.json").json()
    assert (
        "application/pdf"
        in spec["paths"]["/api/papers/{paper_id}/pdf"]["get"]["responses"]["200"]["content"]
    )
    schemas = spec["components"]["schemas"]
    assert "pdf_available" in schemas["PaperDetail"]["properties"]
    assert "pdf_path" not in schemas["PaperDetail"]["properties"]
    assert "matched_fields" in schemas["SearchHit"]["properties"]
