"""Real CPU embeddings, ES vector scores, dual RRF and exact source citations."""

from dataclasses import replace

from elasticsearch import Elasticsearch
from fastapi.testclient import TestClient
import pytest

from backend.app1 import SearchParams, build_search, create_app
from backend.config import Settings
from backend.retrieval import encoder, rrf, vector_candidates, vector_metadata
from elasticsearch.helpers import scan
from backend.tests.test_v2 import REAL_ID

pytestmark = [pytest.mark.integration, pytest.mark.real_data]


@pytest.fixture(scope="module")
def vectors(tmp_path_factory):
    es = Elasticsearch("http://127.0.0.1:9200", request_timeout=60)
    settings = replace(Settings(), runtime_dir=str(tmp_path_factory.mktemp("vector-api")))
    if not es.indices.exists_alias(name=settings.vector_index):
        es.close()
        pytest.skip("real vector build is not published yet")
    base = next(iter(es.indices.get_mapping(index=settings.index)))
    generation, meta = vector_metadata(es, settings, base)
    assert es.count(index=generation)["count"] == meta["chunks"]
    with TestClient(create_app(settings, es)) as api:
        yield api, es, settings, base, generation, meta
    es.close()


def test_vector_papers_dimensions_and_source_offsets(vectors):
    _, es, settings, base, generation, meta = vectors
    assert meta["papers"] == 859 and meta["dimensions"] == 384 and meta["chunks"] > 859
    aggregated = es.search(
        index=generation,
        size=0,
        aggs={"papers": {"cardinality": {"field": "paper_id", "precision_threshold": 40000}}},
    )
    assert aggregated["aggregations"]["papers"]["value"] == 859
    rows = es.search(index=generation, size=20, sort=["chunk_id"])["hits"]["hits"]
    for row in rows:
        c = row["_source"]
        d = es.get(index=base, id=c["paper_id"])["_source"]
        assert c["text"] == d[c["field"]][c["offset_start"] : c["offset_end"]]
        assert len(c["embedding"]) == 384
        assert sum(x * x for x in c["embedding"]) == pytest.approx(1, abs=1e-4)
    flagged = [
        d
        for d in scan(es, index=base, source=["errors"])
        if "unreadable_characters_in_fulltext" in d["_source"].get("errors", [])
    ]
    assert len(flagged) == 4
    for d in flagged:
        assert (
            es.count(
                index=generation,
                query={
                    "bool": {
                        "filter": [
                            {"term": {"paper_id": d["_id"]}},
                            {"term": {"field": "fulltext"}},
                        ]
                    }
                },
            )["count"]
            == 0
        )


def test_dense_score_is_real_cosine(vectors):
    _, es, settings, base, generation, _ = vectors
    params = SearchParams(q="How can MRI measure human brain function?", mode="semantic")
    hits, _ = vector_candidates(es, settings, base, params)
    assert hits and len({h["_source"]["paper_id"] for h in hits}) == len(hits)
    top = hits[0]
    source = es.get(index=generation, id=top["_id"])["_source"]
    q = encoder(settings.model_dir).encode([params.q])[0]
    dot = sum(a * b for a, b in zip(q, source["embedding"]))
    assert top["_score"] == pytest.approx(dot + 1, abs=2e-4)


@pytest.mark.parametrize("mode", ["keyword", "semantic", "hybrid"])
def test_three_actual_modes(vectors, mode):
    api, *_ = vectors
    q = "magnetic" if mode == "keyword" else "brain magnetic resonance imaging"
    r = api.get("/api/search", params={"q": q, "mode": mode, "field": "title", "page_size": 10})
    assert r.status_code == 200, r.text
    body = r.json()
    assert any(d["paper_id"] == REAL_ID for d in body["results"])
    assert body["query"]["mode"] == mode and body["total"] > 0
    assert all(h["score"] > 0 for h in body["results"])
    assert r.headers["X-ScholarLens-Data-Status"] == "real"


def test_hybrid_exact_rrf_of_both_actual_rankings(vectors):
    api, es, settings, base, _, _ = vectors
    params = SearchParams(q="magnetic", field="title", mode="hybrid", page_size=20)
    dense, _ = vector_candidates(es, settings, base, params)
    lexical = build_search(params)
    lexical.update(from_=0, size=1000, sort=[{"_score": "desc"}, {"paper_id": "asc"}])
    keyword = es.search(index=base, **lexical)["hits"]["hits"]
    expected = rrf([h["_id"] for h in keyword], [h["_source"]["paper_id"] for h in dense])
    actual = api.get("/api/search", params=params.model_dump(exclude_none=True)).json()["results"]
    assert [h["paper_id"] for h in actual] == [p for p, _ in expected[:20]]
    assert [h["score"] for h in actual] == pytest.approx([s for _, s in expected[:20]])


@pytest.mark.parametrize("mode", ["semantic", "hybrid"])
def test_vector_pagination_years_and_parameter_effects(vectors, mode):
    api, *_ = vectors
    p = {"q": "brain imaging", "mode": mode, "page_size": 3}
    a = api.get("/api/search", params=p).json()
    b = api.get("/api/search", params={**p, "page": 2}).json()
    assert not {h["paper_id"] for h in a["results"]} & {h["paper_id"] for h in b["results"]}
    filtered = api.get("/api/search", params={**p, "year_from": 2006, "year_to": 2006}).json()
    assert filtered["results"] and all(h["year"] == 2006 for h in filtered["results"])
    for sort in ("year_asc", "year_desc"):
        hits = api.get("/api/search", params={**p, "page_size": 100, "sort": sort}).json()[
            "results"
        ]
        years = [h["year"] for h in hits if h["year"] is not None]
        assert years == sorted(years, reverse=sort == "year_desc")
    assert api.get("/api/search", params={**p, "page": 1001}).status_code == 400
    assert api.get("/api/search", params={**p, "year_from": 9999}).json()["results"] == []


def test_unsupported_semantic_options_and_dependency_state(vectors):
    api, es, settings, _, _, _ = vectors
    for opt in ({"field": "authors"}, {"phrase": True}, {"fuzzy": True}):
        r = api.get("/api/search", params={"q": "MRI", "mode": "semantic", **opt})
        assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_parameter"
    with TestClient(
        create_app(replace(settings, vector_index="scholarlens-missing-vector"), es)
    ) as missing:
        assert missing.get("/api/search?q=MRI&mode=hybrid").status_code == 503
        assert missing.get("/api/search?q=magnetic&field=title").json()["total"] == 1
    assert api.get("/api/capabilities").json()["modules"]["semantic_search"]["status"] == "ready"


@pytest.mark.parametrize("mode", ["semantic", "hybrid"])
def test_real_rag_vectors_are_traceable(vectors, mode):
    api, *_ = vectors
    r = api.post(
        "/api/evidence",
        json={
            "question": "How is magnetic resonance used for brain imaging?",
            "paper_ids": [REAL_ID],
            "mode": mode,
            "top_k": 4,
        },
    )
    assert r.status_code == 200 and r.json(), r.text
    doc = api.get("/api/papers/" + REAL_ID).json()
    for c in r.json():
        field, _, span = c["locator"].split(":")
        start, end = map(int, span.split("-"))
        assert c["paper_id"] == REAL_ID and doc[field][start:end] == c["quote"]
