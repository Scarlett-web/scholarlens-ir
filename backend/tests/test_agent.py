"""Real HTTP workflow; only retrieval and provider responses use controlled fixtures."""
from dataclasses import replace
import json
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

from backend.accounts import Store, problem
from backend.agent_runtime import ResearchAgent
from backend.chunks import chunks
from backend.config import Settings
import backend.rag as rag


def answer(refs):
    return json.dumps({"answer": "Supported " + " ".join("[" + r["chunk_id"] + "]" for r in refs),
                       "citations": [{"chunk_id": r["chunk_id"], "quote": r["quote"]} for r in refs]})


@pytest.fixture
def agent_api(monkeypatch, tmp_path):
    docs = {pid: {"paper_id": pid, "title": "Fixture paper " + pid,
                  "abstract": "Fixture source text.", "fulltext": "A controlled body passage."}
            for pid in ("fixture-paper", "fixture-second")}
    refs = [{"paper_id": c["paper_id"], "paper_title": c["title"], "chunk_id": c["chunk_id"],
             "quote": c["text"], "locator": c["locator"], "relevance_score": 1.0}
            for c in chunks(docs["fixture-paper"])]
    settings = Settings()
    calls = []

    def retrieve(*args):
        calls.append(("retrieve", args[3].question))
        return list(refs)

    def planner(config, question, operation, skill, **kwargs):
        calls.append(("plan", config.ai_api_key))
        assert "untrusted" in skill
        return '{"queries":["planned terms"]}'

    def generate(config, question, evidence, **kwargs):
        calls.append(("generate", config.ai_api_key))
        assert kwargs["validate"] is False and kwargs["deadline"] > 0
        return answer(evidence[:1])

    def authenticate(authorization):
        if authorization not in ("Bearer fixture-a", "Bearer fixture-b"):
            raise problem(401, "unauthorized", "请先登录")
        return {"id": 1 if authorization.endswith("a") else 2}

    monkeypatch.setattr(rag, "retrieve_evidence", retrieve)
    monkeypatch.setattr(rag, "model_plan", planner)
    monkeypatch.setattr(rag, "generate", generate)
    store = Store(str(tmp_path))
    with store.connect() as db:
        for user_id in (1, 2):
            db.execute("INSERT INTO users(id,username,salt,password_hash,created_at) VALUES(?,?,?,?,?)",
                       (user_id, f"fixture{user_id}", "fixture", "fixture", "2026-10-28"))
    app = FastAPI()
    app.include_router(rag.router(None, settings, lambda: ("fixture-index", None),
                                  lambda pid: (docs[pid], None),
                                  store=SimpleNamespace(authenticate=authenticate, connect=store.connect)))
    with TestClient(app) as api:
        yield SimpleNamespace(api=api, docs=docs, refs=refs, calls=calls, settings=settings)


def personal(secret="fixture-only", auth="Bearer fixture-a"):
    return {"Authorization": auth, "x-scholarlens-ai-url": "https://provider.example/v1",
            "x-scholarlens-ai-model": "fixture-model", "x-scholarlens-ai-key": secret}


def run(env, **body):
    return env.api.post("/api/agent/run", headers=personal(), json={"question": "fixture", **body})


def test_agent_endpoint_counts_actual_evidence_and_calls(agent_api):
    response = run(agent_api, stream=True)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["agent"]["grounded"]
    assert data["agent"]["evidence_count"] == data["retrieval"]["evidence_count"] == 3
    assert len(data["citations"]) == 1 and len(data["evidence"]) == 3
    assert [s["tool"] for s in data["agent"]["steps"]] == [
        "plan_research", "search_papers", "search_papers", "verify_sources", "grounded_answer", "citation_guard"]
    assert all(s["status"] == "done" and s["elapsed_ms"] >= 0 for s in data["agent"]["steps"])
    assert "fixture-only" not in response.text and "provider.example" not in response.text


def test_agent_endpoint_does_not_generate_when_no_evidence(agent_api, monkeypatch):
    monkeypatch.setattr(rag, "retrieve_evidence", lambda *args: [])
    data = run(agent_api).json()
    assert data["evidence_status"] == "insufficient_evidence"
    assert not data["answer"] and not data["agent"]["grounded"]
    assert not any(name == "generate" for name, _ in agent_api.calls)
    assert "grounded_answer" not in [s["tool"] for s in data["agent"]["steps"]]


@pytest.mark.parametrize("operation,papers", [("summarize", None), ("compare", ["fixture-paper"])])
def test_agent_endpoint_validates_operation_scope(agent_api, operation, papers):
    assert run(agent_api, operation=operation, paper_ids=papers).status_code == 400


def test_agent_evidence_mode_never_uses_a_model(agent_api):
    for headers in ({}, personal()):
        response = agent_api.api.post("/api/agent/run", headers=headers,
                                      json={"question": "fixture", "operation": "evidence"})
        assert response.status_code == 200
        data = response.json()
        assert data["evidence_status"] == "evidence_only" and len(data["evidence"]) == 3
        assert data["model"]["status"] == "not_called"
    assert all(name == "retrieve" for name, _ in agent_api.calls)


def test_agent_without_personal_config_returns_original_sources(agent_api):
    data = agent_api.api.post("/api/agent/run", json={"question": "fixture"}).json()
    assert data["evidence_status"] == "evidence_only"
    assert data["agent"]["warnings"] and not data["answer"]
    assert not agent_api.settings.ai_api_key


def test_agent_model_plan_drives_actual_searches(agent_api):
    run(agent_api)
    assert ("retrieve", "planned terms") in agent_api.calls
    assert ("retrieve", "fixture") in agent_api.calls


def test_agent_invalid_plan_falls_back_without_executing_tools(agent_api, monkeypatch):
    monkeypatch.setattr(rag, "model_plan", lambda *args, **kwargs: '{"tool":"shell","command":"do not execute"}')
    data = run(agent_api).json()
    assert data["agent"]["steps"][0]["status"] == "error"
    assert data["agent"]["warnings"]
    assert ("retrieve", "fixture") in agent_api.calls
    assert all(s["tool"] != "shell" for s in data["agent"]["steps"])


def test_agent_rejects_altered_source_quote(agent_api):
    agent_api.refs[0]["quote"] = "fabricated text absent from source"
    data = run(agent_api).json()
    assert len(data["evidence"]) == 2
    assert all(r["quote"] != "fabricated text absent from source" for r in data["evidence"])


def test_agent_repairs_invalid_citations_once_without_leaking_draft(agent_api, monkeypatch):
    drafts = []

    def invalid(*args, **kwargs):
        drafts.append(1)
        return '{"answer":"UNVERIFIED DRAFT [chunk:fake]","citations":[{"chunk_id":"chunk:fake","quote":"fake"}]}'

    monkeypatch.setattr(rag, "generate", invalid)
    response = run(agent_api)
    data = response.json()
    assert len(drafts) == 2 and len(data["evidence"]) == 3
    assert not data["answer"] and not data["citations"]
    assert data["evidence_status"] == "insufficient_evidence"
    assert "UNVERIFIED DRAFT" not in response.text
    assert sum(s["tool"] == "citation_guard" and s["status"] == "error" for s in data["agent"]["steps"]) == 2


def test_agent_successful_repair_is_validated(agent_api, monkeypatch):
    drafts = []

    def repairing(config, question, refs, **kwargs):
        drafts.append(question)
        return '{"answer":"bad"}' if len(drafts) == 1 else answer(refs[:1])

    monkeypatch.setattr(rag, "generate", repairing)
    data = run(agent_api).json()
    assert len(drafts) == 2 and "Repair invalid citations" in drafts[1]
    assert data["evidence_status"] == "sufficient" and data["agent"]["grounded"]


def test_agent_provider_failure_preserves_evidence(agent_api, monkeypatch):
    def unavailable(*args, **kwargs):
        raise problem(502, "ai_upstream_error", "模型暂不可用")

    monkeypatch.setattr(rag, "generate", unavailable)
    data = run(agent_api).json()
    assert data["evidence_status"] == "provider_unavailable"
    assert len(data["evidence"]) == 3 and not data["answer"]
    assert data["model"]["status"] == "attempted"
    assert sum(s["tool"] == "grounded_answer" for s in data["agent"]["steps"]) == 1


def test_agent_compare_requires_citations_from_every_paper(agent_api, monkeypatch):
    papers = list(agent_api.docs)
    data = run(agent_api, operation="compare", paper_ids=papers, top_k=10).json()
    assert not data["answer"] and len(data["evidence"]) == 4
    monkeypatch.setattr(rag, "generate", lambda config, question, refs, **kwargs: answer(refs))
    data = run(agent_api, operation="compare", paper_ids=papers, top_k=10).json()
    assert data["evidence_status"] == "sufficient"
    assert {c["paper_id"] for c in data["citations"]} == set(papers)


def test_agent_compare_missing_paper_keeps_other_sources(agent_api):
    agent_api.docs["fixture-second"].update(abstract="", fulltext="")
    data = run(agent_api, operation="compare", paper_ids=list(agent_api.docs), top_k=10).json()
    assert data["evidence_status"] == "insufficient_evidence" and len(data["evidence"]) == 2
    assert not any(name == "generate" for name, _ in agent_api.calls)


def test_agent_personal_configuration_is_authenticated_and_isolated(agent_api):
    body = {"question": "fixture"}
    assert agent_api.api.post("/api/agent/run", headers=personal(auth=""), json=body).status_code == 401
    for auth, secret in [("Bearer fixture-a", "user-a-only"), ("Bearer fixture-b", "user-b-only")]:
        response = agent_api.api.post("/api/agent/run", headers=personal(secret, auth), json=body)
        assert response.status_code == 200 and secret not in response.text
    assert [secret for name, secret in agent_api.calls if name == "generate"] == ["user-a-only", "user-b-only"]
    assert not agent_api.settings.ai_api_key
    assert agent_api.api.post("/api/agent/run", json=body).json()["evidence_status"] == "evidence_only"


def test_agent_reopened_conversation_keeps_evidence_and_owner_boundary(agent_api, monkeypatch):
    created = agent_api.api.post("/api/ai/conversations", headers=personal(), json={"title": "Fixture research"})
    conversation = created.json()["id"]

    def unavailable(*args, **kwargs):
        raise problem(502, "ai_upstream_error", "模型暂不可用")

    monkeypatch.setattr(rag, "generate", unavailable)
    response = run(agent_api, conversation_id=conversation)
    assert response.status_code == 200 and response.json()["evidence_status"] == "provider_unavailable"
    path = "/api/ai/conversations/" + conversation + "/messages"
    messages = agent_api.api.get(path, headers=personal()).json()
    assert len(messages) == 2 and messages[1]["role"] == "assistant"
    assert not messages[1]["content"] and len(messages[1]["citations"]) == 3
    assert agent_api.api.get(path, headers=personal(auth="Bearer fixture-b")).status_code == 404


def test_agent_tool_and_deadline_budgets_block_callbacks():
    runner = ResearchAgent(lambda q: [], lambda refs, scope: refs, lambda refs, n: "", lambda *a: ("", []))
    runner.policy = replace(runner.policy, max_tool_calls=1)
    runner.call("search_papers", "first", lambda: [])
    called = []
    with pytest.raises(HTTPException) as error:
        runner.call("search_papers", "second", lambda: called.append(True))
    assert error.value.status_code == 429 and not called and len(runner.steps) == 1
    runner.steps.clear()
    runner.deadline = 0
    with pytest.raises(HTTPException):
        runner.call("search_papers", "late", lambda: called.append(True))
    with pytest.raises(ValueError):
        runner.call("shell", "unknown", lambda: called.append(True))
    assert not called
