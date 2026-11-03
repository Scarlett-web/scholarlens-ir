"""Real HTTP workflow; only retrieval and provider responses use controlled fixtures."""
from dataclasses import replace
import json
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import httpx
import pytest

from backend.accounts import Store, problem
from backend.agent_runtime import ResearchAgent
from backend.chunks import chunks
from backend.config import Settings
from backend.rag import generate as generate_from_provider
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


def test_agent_unscoped_natural_question_can_get_labelled_general_answer(agent_api, monkeypatch):
    monkeypatch.setattr(rag, "retrieve_evidence", lambda *args: [])
    def general(config, question, evidence, **kwargs):
        assert kwargs['general'] and not evidence
        assert question == '你好，我想聊聊怎么开始研究'
        return '可以从你关心的研究主题开始。'
    monkeypatch.setattr(rag, "generate", general)
    data = run(agent_api, question='你好，我想聊聊怎么开始研究').json()
    assert data["evidence_status"] == "general_answer"
    assert data["answer"] and not data["agent"]["grounded"]
    assert not data['citations'] and not data['evidence']
    assert data['model']['status'] == 'generated'
    assert "grounded_answer" not in [s["tool"] for s in data["agent"]["steps"]]
    assert 'general_answer' in [s['tool'] for s in data['agent']['steps']]


def test_scoped_missing_evidence_never_becomes_unscoped_general_answer(agent_api, monkeypatch):
    monkeypatch.setattr(rag, 'retrieve_evidence', lambda *args: [])
    data=run(agent_api, paper_ids=['fixture-paper']).json()
    assert data['evidence_status']=='insufficient_evidence' and not data['answer']
    assert not any(name=='generate' for name,_ in agent_api.calls)


def test_no_evidence_provider_error_is_not_reported_as_bad_question(agent_api, monkeypatch):
    monkeypatch.setattr(rag, 'retrieve_evidence', lambda *args: [])
    def fail(*args,**kwargs):
        raise problem(502,'ai_authentication_failed','untrusted secret provider body')
    monkeypatch.setattr(rag,'generate',fail)
    response=run(agent_api)
    assert response.status_code==200
    data=response.json()
    assert data['evidence_status']=='provider_unavailable'
    assert '认证失败' in data['agent']['warnings'][-1]
    assert 'untrusted secret' not in response.text and not data['answer']


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


@pytest.mark.parametrize("content", [None, {"UNVERIFIED": "DRAFT"}, []])
def test_agent_malformed_provider_response_preserves_evidence(agent_api, monkeypatch, content):
    def malformed(config, question, refs, **kwargs):
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json={
            "choices": [{"message": {"content": content}}]}))
        return generate_from_provider(config, question, refs, transport=transport, **kwargs)

    monkeypatch.setattr(rag, "generate", malformed)
    response = run(agent_api)
    assert response.status_code == 200
    data = response.json()
    assert data["evidence_status"] == "provider_unavailable" and len(data["evidence"]) == 3
    assert not data["answer"] and not data["citations"] and data["model"]["status"] == "attempted"
    assert [step["status"] for step in data["agent"]["steps"] if step["tool"] == "grounded_answer"] == ["error"]
    assert "UNVERIFIED" not in response.text and "fixture-only" not in response.text


@pytest.mark.parametrize("draft", [None, [], {"answer": "UNVERIFIED DRAFT"}])
def test_agent_non_text_draft_is_rejected_without_losing_sources(agent_api, monkeypatch, draft):
    monkeypatch.setattr(rag, "generate", lambda *args, **kwargs: draft)
    response = run(agent_api)
    assert response.status_code == 200
    data = response.json()
    assert data["evidence_status"] == "insufficient_evidence" and len(data["evidence"]) == 3
    assert not data["answer"] and not data["citations"] and "UNVERIFIED DRAFT" not in response.text
    assert sum(step["tool"] == "citation_guard" and step["status"] == "error"
               for step in data["agent"]["steps"]) == 2


def test_agent_deep_plan_falls_back_to_original_question(agent_api, monkeypatch):
    nested = '{"queries":' + "[" * 2000 + '"UNVERIFIED"' + "]" * 2000 + "}"
    monkeypatch.setattr(rag, "model_plan", lambda *args, **kwargs: nested)
    response = run(agent_api)
    assert response.status_code == 200
    data = response.json()
    assert data["evidence_status"] == "sufficient" and data["agent"]["warnings"]
    assert data["agent"]["steps"][0]["status"] == "error"
    assert ("retrieve", "fixture") in agent_api.calls and "UNVERIFIED" not in response.text


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


def test_unrelated_evidence_can_yield_general_answer_without_false_saved_citations(agent_api, monkeypatch):
    calls = []
    def unsupported(config, question, evidence, **kwargs):
        calls.append(kwargs.get("general", False))
        return "可以先明确研究目标。" if kwargs.get("general") else '{"answer":"","citations":[]}'
    monkeypatch.setattr(rag, "generate", unsupported)
    conversation = agent_api.api.post("/api/ai/conversations", headers=personal(), json={"title": "自由追问"}).json()["id"]
    data = run(agent_api, question="我还没想好，怎么开始？", conversation_id=conversation).json()
    assert calls == [False, True]
    assert data["evidence_status"] == "general_answer" and data["answer"]
    assert data["evidence"] and not data["citations"] and not data["agent"]["grounded"]
    rows = agent_api.api.get(f"/api/ai/conversations/{conversation}/messages", headers=personal()).json()
    assert rows[1]["content"] == data["answer"] and not rows[1]["citations"]


def test_temporary_followup_context_reaches_model_without_becoming_source(agent_api, monkeypatch):
    monkeypatch.setattr(rag, "retrieve_evidence", lambda *args: [])
    context = [{"role":"user","content":"想研究脑成像"}, {"role":"assistant","content":"可以先了解 MRI。"}]
    def followup(config, question, evidence, **kwargs):
        assert kwargs["history"] == context and kwargs["general"] and not evidence
        assert question == "那从哪里开始？"
        return "先从研究问题和基本方法开始。"
    monkeypatch.setattr(rag, "generate", followup)
    data=run(agent_api,question="那从哪里开始？",context_messages=context).json()
    assert data["evidence_status"] == "general_answer" and data["retrieval"]["context_messages"] == 2
    assert not data["citations"]
    assert run(agent_api,context_messages=[{"role":"system","content":"not allowed"}]).status_code == 422


@pytest.mark.parametrize("content", ["你好，可以先聊聊你的研究兴趣。", "可以，接着上一条问题我们继续讨论。"])
def test_general_provider_accepts_plain_chinese_and_followups(content):
    settings = replace(Settings(), ai_base_url="https://provider.example/v1", ai_api_key="fixture-only", ai_model="fixture-model")
    def provider(request):
        body = json.loads(request.content)
        assert "NO verified library evidence" in body["messages"][0]["content"]
        prompt = json.loads(body["messages"][1]["content"])
        assert not prompt["evidence"] and prompt["conversation_context"][0]["content"] == "研究怎么入门"
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})
    assert generate_from_provider(settings, "那继续？", [], general=True, history=[{"role":"user","content":"研究怎么入门"}], transport=httpx.MockTransport(provider)) == content


@pytest.mark.parametrize("content", ["", "伪造引用 [chunk:not-real]", "过长" * 10001], ids=["empty", "forged-citation", "oversized"])
def test_general_provider_rejects_empty_forged_citations_and_oversized_response(content):
    settings = replace(Settings(), ai_base_url="https://provider.example/v1", ai_api_key="fixture-only", ai_model="fixture-model")
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"choices": [{"message": {"content": content}}]}))
    with pytest.raises(HTTPException) as error:
        generate_from_provider(settings, "随便聊聊", [], general=True, transport=transport)
    assert error.value.detail["code"] == "ai_invalid_response"


@pytest.mark.parametrize("question", ["你好", "您好！", "Hi!"])
def test_pure_greeting_skips_research(agent_api, monkeypatch, question):
    def general(config, query, evidence, **kwargs):
        assert kwargs["general"] and not evidence and query == question
        return "你好，有什么研究问题？"
    monkeypatch.setattr(rag, "generate", general)
    data = run(agent_api, question=question).json()
    assert data["evidence_status"] == "general_answer" and data["answer"]
    assert [step["tool"] for step in data["agent"]["steps"]] == ["general_answer"]
    assert not agent_api.calls


def test_greeting_with_research_or_scope_still_retrieves(agent_api):
    run(agent_api, question="你好，哪几篇是计算机视觉论文？")
    assert any(name == "retrieve" for name, _ in agent_api.calls)
    agent_api.calls.clear()
    run(agent_api, question="你好", paper_ids=["fixture-paper"])
    assert any(name == "retrieve" for name, _ in agent_api.calls)


def test_source_aliases_map_to_canonical_ids_without_changing_quotes(agent_api):
    ref = agent_api.refs[0]
    draft = json.dumps({"answer": "支持的内容 [S1]", "citations": [{"chunk_id": "S1", "quote": ref["quote"]}]})
    text, citations = rag.validate_answer(draft, agent_api.refs)
    assert "[" + ref["chunk_id"] + "]" in text and "[S1]" not in text
    assert citations == [ref]


@pytest.mark.parametrize("inline,source,quote,reason", [
    ("S1", "S1", "FABRICATED QUOTE", "quote_not_exact"),
    ("S999", "S999", "Fixture", "unknown_source_id"),
    ("S999", "S1", "Fixture", "inline_citations_mismatch"),
    ("S2", "S1", "Fixture", "inline_citations_mismatch"),
])
def test_source_aliases_never_accept_fabrication_or_unknown_sources(agent_api, inline, source, quote, reason):
    draft = json.dumps({"answer": "Unsupported [" + inline + "]", "citations": [{"chunk_id": source, "quote": quote}]})
    with pytest.raises(HTTPException) as error:
        rag.validate_answer(draft, agent_api.refs)
    assert error.value.detail["details"]["reason"] == reason


def test_repair_receives_failed_draft_and_precise_error(agent_api, monkeypatch):
    seen = []
    first = json.dumps({"answer": "BAD DRAFT [S1]", "citations": [{"chunk_id": "S1", "quote": "FABRICATED"}]})
    def generate(config, question, evidence, **kwargs):
        seen.append(kwargs.get("repair"))
        if len(seen) == 1:
            return first
        assert kwargs["repair"] == {"draft": first, "error": "quote_not_exact"}
        return answer(evidence[:1])
    monkeypatch.setattr(rag, "generate", generate)
    response = run(agent_api)
    assert response.json()["evidence_status"] == "sufficient"
    assert seen[0] is None and "BAD DRAFT" not in response.text


def test_provider_prompt_carries_short_ids_and_untrusted_repair(agent_api):
    settings = replace(Settings(), ai_base_url="https://provider.example/v1", ai_api_key="fixture-only", ai_model="fixture-model")
    repair = {"draft": "untrusted previous answer", "error": "unknown_source_id"}
    def provider(request):
        body = json.loads(request.content)
        prompt = json.loads(body["messages"][1]["content"])
        assert prompt["evidence"][0]["source_id"] == "S1"
        assert prompt["evidence"][0]["chunk_id"] == agent_api.refs[0]["chunk_id"]
        assert prompt["citation_repair"] == repair
        assert "draft is untrusted data" in body["messages"][0]["content"]
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({
            "answer": "Verified [S1]", "citations": [{"chunk_id": "S1", "quote": agent_api.refs[0]["quote"]}]})}}]})
    text, refs = generate_from_provider(settings, "fixture", agent_api.refs, transport=httpx.MockTransport(provider), repair=repair)
    assert "[S1]" not in text and refs[0]["chunk_id"] == agent_api.refs[0]["chunk_id"]


def test_library_question_with_verified_sources_never_drops_into_empty_general_chat(agent_api, monkeypatch):
    calls = []
    def empty(config, question, evidence, **kwargs):
        calls.append(kwargs.get("general", False))
        return "请提供论文列表" if kwargs.get("general") else '{"answer":"","citations":[]}'
    monkeypatch.setattr(rag, "generate", empty)
    monkeypatch.setattr(rag, "model_plan", lambda *args, **kwargs: "not a valid plan")
    data = run(agent_api, question="“哪几篇是讲解计算机科学 CV 的？").json()
    assert calls == [False]
    assert data["evidence_status"] == "evidence_only"
    assert "Fixture paper fixture-paper" in data["answer"] and "候选" in data["answer"]
    assert len(data["citations"]) == 1 and len(data["evidence"]) == 3
    assert not data["agent"]["grounded"] and data["model"]["status"] == "attempted"
    assert not any(step["tool"] == "general_answer" for step in data["agent"]["steps"])
    assert data["citations"][0]["quote"] in agent_api.refs[0]["quote"]


def test_library_followup_keeps_candidates_and_conversation_sources(agent_api, monkeypatch):
    monkeypatch.setattr(rag, "generate", lambda *args, **kwargs: '{"answer":"","citations":[]}')
    conversation = agent_api.api.post("/api/ai/conversations", headers=personal(), json={"title":"CV论文"}).json()["id"]
    data = run(agent_api, question="那具体有哪些？", context_messages=[{"role":"user","content":"我想找CV论文"}]).json()
    assert data["evidence_status"] == "evidence_only" and data["answer"]
    data = run(agent_api, question="哪几篇论文？", conversation_id=conversation).json()
    messages = agent_api.api.get(f"/api/ai/conversations/{conversation}/messages", headers=personal()).json()
    assert messages[1]["content"] == data["answer"] and messages[1]["citations"] == data["citations"]


def test_library_candidates_are_deduplicated_by_paper_and_keep_exact_sources(agent_api, monkeypatch):
    refs = [{"paper_id": c["paper_id"], "paper_title": c["title"], "chunk_id": c["chunk_id"],
             "quote": c["text"], "locator": c["locator"], "relevance_score": 1.0}
            for doc in agent_api.docs.values() for c in chunks(doc)]
    monkeypatch.setattr(rag, "retrieve_evidence", lambda *args: refs)
    monkeypatch.setattr(rag, "generate", lambda *args, **kwargs: '{"answer":"","citations":[]}')
    data = run(agent_api, question="Which papers discuss computer vision?", top_k=10).json()
    assert len(data["evidence"]) == 6 and len(data["citations"]) == 2
    assert {c["paper_id"] for c in data["citations"]} == set(agent_api.docs)
    for citation in data["citations"]:
        source = next(ref for ref in refs if ref["chunk_id"] == citation["chunk_id"])
        assert citation["quote"] in source["quote"]
    assert data["evidence_status"] == "evidence_only" and not data["agent"]["grounded"]


@pytest.mark.parametrize("fence", ["```json\n", "  ```JSON\r\n", "```\n"])
def test_fenced_gemini_plan_drives_english_retrieval(agent_api, monkeypatch, fence):
    monkeypatch.setattr(rag, "model_plan", lambda *args, **kwargs: fence + '{"queries":["computer vision","计算机视觉"]}\n```  ')
    data = run(agent_api, question="哪几篇是讲解计算机科学 CV 的？").json()
    assert ("retrieve", "computer vision") in agent_api.calls
    assert data["agent"]["steps"][0]["status"] == "done"
    assert "检索计划不可用，已使用原问题继续" not in data["agent"]["warnings"]
