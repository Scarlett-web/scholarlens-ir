from backend.agent import AGENT_NAME, finish_plan, plan, trace
from backend.config import Settings
from dataclasses import replace
from fastapi import FastAPI
from fastapi.testclient import TestClient
import backend.rag as rag
import pytest


def test_agent_plan_is_bounded_and_explicit():
    steps = plan("compare", "compare methods", ["p1", "p2"])
    assert [step["tool"] for step in steps] == [
        "search_papers",
        "retrieve_evidence",
        "grounded_answer",
        "citation_guard",
    ]
    assert steps[0]["status"] == "done"


def test_agent_trace_reports_insufficient_evidence_without_claiming_grounding():
    result = trace("ask", "unknown", None, 0, False)
    assert result["name"] == AGENT_NAME
    assert result["grounded"] is False
    assert result["steps"][1]["status"] == "empty"
    assert result["steps"][2]["status"] == "skipped"


def test_finish_plan_marks_answer_and_guard_after_evidence():
    result = finish_plan(plan("ask", "question", None), 2, True)
    assert [step["status"] for step in result] == ["done", "done", "done", "done"]


@pytest.fixture
def agent_api(monkeypatch):
    """Exercise the HTTP contract with isolated retrieval and provider fixtures."""
    settings = replace(Settings(), ai_base_url="https://provider.example/v1",
                       ai_api_key="fixture-only", ai_model="fixture-model")
    refs = [{"paper_id": "fixture-paper", "paper_title": "Fixture paper",
             "chunk_id": f"chunk:fixture:{i}", "quote": "Fixture source text.",
             "locator": "abstract", "relevance_score": 1.0} for i in range(3)]
    monkeypatch.setattr(rag, "retrieve_evidence", lambda *args: list(refs))
    monkeypatch.setattr(rag, "generate", lambda *args: ("Supported [chunk:fixture:0]", refs[:1]))
    app = FastAPI()
    app.include_router(rag.router(None, settings, lambda: ("fixture-index", None), None))
    with TestClient(app) as api:
        yield api


def test_agent_endpoint_counts_retrieved_evidence_separately_from_citations(agent_api):
    response = agent_api.post("/api/agent/run", json={"question": "fixture", "stream": True})
    assert response.status_code == 200
    data = response.json()
    assert data["agent"]["grounded"] is True
    assert data["agent"]["evidence_count"] == data["retrieval"]["evidence_count"] == 3
    assert len(data["citations"]) == 1
    assert "fixture-only" not in response.text


def test_agent_endpoint_does_not_generate_when_no_evidence(agent_api, monkeypatch):
    monkeypatch.setattr(rag, "retrieve_evidence", lambda *args: [])
    def unexpected_generation(*args):
        pytest.fail("No evidence must not call the provider")
    monkeypatch.setattr(rag, "generate", unexpected_generation)
    response = agent_api.post("/api/agent/run", json={"question": "no sources"})
    assert response.status_code == 200
    data = response.json()
    assert data["evidence_status"] == "insufficient_evidence"
    assert data["agent"]["grounded"] is False
    assert data["agent"]["steps"][2]["status"] == "skipped"


@pytest.mark.parametrize("operation,papers", [("summarize", None), ("compare", ["only-one"])])
def test_agent_endpoint_validates_operation_scope(agent_api, operation, papers):
    response = agent_api.post("/api/agent/run", json={
        "question": "fixture", "operation": operation, "paper_ids": papers,
    })
    assert response.status_code == 400
