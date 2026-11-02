"""Controlled candidate, validation and protection tests without index writes."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.spellcheck import corrections, router
from backend.spellcheck import edit_distance


def test_typing_can_split_existing_joined_word_without_rewriting_results():
    class Joined(Corpus):
        def count(self, *, index, query):
            return {"count": {"machinelearning": 1, "machine learning": 10}.get(query["text"], 0)}

    assert corrections(Joined(), "g", "machinelearning", "all", None, None, 3, build) == []
    assert (
        corrections(
            Joined(), "g", "machinelearning", "all", None, None, 3, build, require_empty=False
        )[0]["text"]
        == "machine learning"
    )


def test_all_uses_body_only_candidates():
    class Body(Corpus):
        def search(self, **kwargs):
            return {
                "suggest": {
                    "0_body": [{"options": [{"text": "machine", "score": 0.9, "freq": 10}]}]
                }
            }

    assert (
        corrections(Body(), "g", "machein learning", "all", None, None, 3, build)[0]["text"]
        == "machine learning"
    )


class Corpus:
    def __init__(self, original_count=0):
        self.calls = []
        self.original_count = original_count

    def count(self, *, index, query):
        self.calls.append((index, query))
        text = query["text"]
        return {"count": 12 if text == "machine learning" else self.original_count}

    def search(self, **kwargs):
        return {
            "suggest": {
                "0": [{"options": [{"text": "machine", "score": 0.9, "freq": 10}]}],
                "1": [{"options": []}],
            }
        }


def build(text, field, start, end):
    return {"query": {"text": text, "field": field, "from": start, "to": end}}


@pytest.mark.parametrize("query", ["machien learning", "machin learning", "machinne learning"])
def test_candidates_verified_and_filters_preserved(query):
    es = Corpus()
    result = corrections(es, "generation-a", query, "title", 2000, 2020, 3, build)
    assert result == [
        {"text": "machine learning", "field": "title", "kind": "spelling", "matched_count": 12}
    ]
    assert es.calls[-1] == (
        "generation-a",
        {"text": "machine learning", "field": "title", "from": 2000, "to": 2020},
    )


def test_correct_query_never_changes():
    es = Corpus(original_count=5)
    assert corrections(es, "g", "machine learning", "all", None, None, 3, build) == []
    assert len(es.calls) == 1


@pytest.mark.parametrize(
    "text,field",
    [
        ("MRI", "all"),
        ("10.1234/abc", "all"),
        ("source-sha256:abc", "all"),
        ("中文 检索", "all"),
        ("2026", "all"),
        ("machien learning", "authors"),
        ("machien learning", "date"),
        ("a " * 9, "all"),
    ],
)
def test_protected_queries(text, field):
    es = Corpus()
    assert corrections(es, "g", text, field, None, None, 3, build) == []
    assert not es.calls


def test_no_candidates_and_candidates_without_hits():
    es = Corpus()
    es.search = lambda **kwargs: {"suggest": {}}
    assert corrections(es, "g", "unknownword", "all", None, None, 3, build) == []
    es = Corpus()
    assert corrections(es, "g", "machien nonexistent", "all", None, None, 3, build) == []


def test_endpoint_limits_and_semantic_skip():
    app = FastAPI()
    app.include_router(router(Corpus(), lambda: ("g", {}), build))
    with TestClient(app) as client:
        assert (
            client.get("/api/spellcheck", params={"q": "machien learning"}).json()["suggestions"][
                0
            ]["text"]
            == "machine learning"
        )
        assert (
            client.get(
                "/api/spellcheck", params={"q": "machien learning", "mode": "semantic"}
            ).json()["suggestions"]
            == []
        )
        assert (
            client.get(
                "/api/spellcheck", params={"q": "test", "year_from": 2020, "year_to": 2000}
            ).status_code
            == 400
        )
        assert client.get("/api/spellcheck", params={"q": "x" * 201}).status_code == 422
        assert client.get("/api/spellcheck", params={"q": "test", "limit": 4}).status_code == 422


def test_cold_suggestion_cache_keeps_requested_field(monkeypatch):
    import backend.discovery as discovery

    monkeypatch.setattr(
        discovery,
        "scan",
        lambda *args, **kwargs: iter(
            [{"_source": {"paper_id": "p", "title": "Machine Learning", "authors": ["An Author"]}}]
        ),
    )
    app = FastAPI()
    app.include_router(discovery.router(Corpus(), lambda: ("g", {}), build))
    with TestClient(app) as client:
        for _ in range(2):
            data = client.get(
                "/api/suggest", params={"q": "machien learning", "field": "all", "limit": 5}
            ).json()
            assert data["suggestions"][0]["kind"] == "spelling"
            assert data["suggestions"][0]["field"] == "all"


@pytest.mark.parametrize(
    "wrong,right",
    [
        ("machein learning", "machine learning"),
        ("machien learning", "machine learning"),
        ("machin learning", "machine learning"),
        ("machinne learning", "machine learning"),
        ("mxchine learning", "machine learning"),
        ("infomration retrieval", "information retrieval"),
        ("information retrival", "information retrieval"),
        ("neurla networks", "neural networks"),
        ("quantm computing", "quantum computing"),
        ("magnetc resonance", "magnetic resonance"),
        ("climte change", "climate change"),
        ("machein learnign", "machine learning"),
        ("infomration retrival systmes", "information retrieval systems"),
        ("machinelearning", "machine learning"),
        ("mach ine learning", "machine learning"),
    ],
)
def test_multiple_error_types_and_domains(wrong, right):
    # Fixtures simulate supplied ES candidates; production has no replacement table.
    expected = (
        dict(zip(wrong.split(), right.split())) if len(wrong.split()) == len(right.split()) else {}
    )

    class Vocabulary(Corpus):
        def count(self, *, index, query):
            self.calls.append((index, query))
            return {"count": 5 if query["text"] == right else 0}

        def search(self, **kwargs):
            return {
                "suggest": {
                    key: [
                        {
                            "options": [{"text": expected[item["text"]], "score": 0.9, "freq": 10}]
                            if item["text"] in expected
                            else []
                        }
                    ]
                    for key, item in kwargs["suggest"].items()
                }
            }

    es = Vocabulary()
    results = corrections(es, "g", wrong, "all", None, None, 3, build)
    assert right in [r["text"] for r in results]
    assert len(es.calls) <= 37  # original query plus at most 36 verified candidates


def test_real_word_fallback_and_distance():
    assert edit_distance("machein", "machine") == 2
    assert edit_distance("neurla", "neural") == 1

    class ExistingWord(Corpus):
        def search(self, **kwargs):
            always = next(iter(kwargs["suggest"].values()))["term"]["suggest_mode"] == "always"
            return {
                "suggest": {
                    "0": [
                        {
                            "options": [{"text": "machine", "score": 0.9, "freq": 10}]
                            if always
                            else []
                        }
                    ]
                }
            }

    assert (
        corrections(ExistingWord(), "g", "marine learning", "all", None, None, 3, build)[0]["text"]
        == "machine learning"
    )
