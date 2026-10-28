"""Untrusted provider envelopes fail closed without losing the agent's sources."""
from dataclasses import replace
import json

from fastapi import HTTPException
import httpx
import pytest

from backend.agent_runtime import model_plan
from backend.config import Settings
from backend.rag import generate, validate_answer
from backend.ai_responses import provider_content


def provider_settings(tmp_path):
    return replace(Settings(), runtime_dir=str(tmp_path), ai_base_url="https://provider.example/v1",
                   ai_model="fixture-model", ai_api_key="fixture-only-secret")


def call_provider(settings, transport, operation):
    if operation == "plan":
        return model_plan(settings, "fixture", "ask", "fixture skill", transport=transport)
    return generate(settings, "fixture", [], transport=transport, validate=operation == "answer")


def assert_redacted(error, operation):
    assert error.value.status_code == 502
    expected = "agent_planner_unavailable" if operation == "plan" else "ai_invalid_response"
    assert error.value.detail["code"] == expected
    assert "UNTRUSTED_BODY" not in json.dumps(error.value.detail)
    assert "fixture-only-secret" not in json.dumps(error.value.detail)


@pytest.mark.parametrize("operation", ["answer", "draft", "plan"])
@pytest.mark.parametrize("content", [None, [], {"UNTRUSTED_BODY": "data"}, 7, True,
                                     [{"type": "text", "text": "UNTRUSTED_BODY"}]])
def test_non_text_chat_content_is_a_controlled_error(tmp_path, operation, content):
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={
        "choices": [{"message": {"content": content}}]}))
    with pytest.raises(HTTPException) as error:
        call_provider(provider_settings(tmp_path), transport, operation)
    assert_redacted(error, operation)


@pytest.mark.parametrize("operation", ["answer", "plan"])
@pytest.mark.parametrize("envelope", [None, [], {}, {"choices": []}, {"choices": [None]},
                                      {"choices": [{"message": None}]}])
def test_malformed_envelopes_are_controlled_errors(tmp_path, operation, envelope):
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=envelope)
                                    if envelope is not None else httpx.Response(200, content=b"null"))
    with pytest.raises(HTTPException) as error:
        call_provider(provider_settings(tmp_path), transport, operation)
    assert_redacted(error, operation)


@pytest.mark.parametrize("operation", ["answer", "draft", "plan"])
def test_deep_provider_envelope_is_a_controlled_error(tmp_path, operation):
    raw = "[" * 2000 + '"UNTRUSTED_BODY"' + "]" * 2000
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=raw))
    with pytest.raises(HTTPException) as error:
        call_provider(provider_settings(tmp_path), transport, operation)
    assert_redacted(error, operation)


def test_deep_answer_json_is_a_validation_error():
    with pytest.raises(ValueError):
        validate_answer("[" * 2000 + '"UNTRUSTED_BODY"' + "]" * 2000, [])


@pytest.mark.parametrize("fenced", [False, True])
def test_valid_text_json_and_fenced_answers_remain_compatible(tmp_path, fenced):
    ref = {"chunk_id": "chunk:fixture", "quote": "Fixture source text."}
    draft = json.dumps({"answer": "Supported [chunk:fixture]", "citations": [ref]})
    content = "```json\n" + draft + "\n```" if fenced else draft
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={
        "choices": [{"message": {"content": content}}]}))
    answer, citations = generate(provider_settings(tmp_path), "fixture", [ref], transport=transport)
    assert answer == "Supported [chunk:fixture]" and citations == [ref]


def response_envelope(text):
    return {"status": "completed", "output": [
        {"type": "reasoning", "summary": [{"type": "summary_text", "text": "Do not display"}]},
        {"type": "message", "role": "assistant", "status": "completed",
         "content": [{"type": "output_text", "text": text}]}]}


@pytest.mark.parametrize("operation", ["answer", "draft", "plan"])
def test_responses_protocol_reaches_planner_and_answer_without_chat_fields(tmp_path, operation):
    config = replace(provider_settings(tmp_path), ai_protocol="responses")
    ref = {"chunk_id": "chunk:fixture", "quote": "Fixture source text."}
    text = json.dumps({"answer": "Supported [chunk:fixture]", "citations": [ref]}) if operation == "answer" else '{"queries":["fixture"]}'
    seen = []
    def reply(request):
        body = json.loads(request.content)
        seen.append(body)
        assert request.url.path == "/v1/responses"
        assert body["model"] == "fixture-model" and body["store"] is False and body["stream"] is False
        assert body["input"][0]["role"] == "system" and len(body["input"]) == 2
        assert "messages" not in body and "max_completion_tokens" not in body and "max_tokens" not in body
        assert 1 <= body["max_output_tokens"] <= 800
        return httpx.Response(200, json=response_envelope(text))
    transport = httpx.MockTransport(reply)
    result = (model_plan(config, "fixture", "ask", "skill", transport=transport) if operation == "plan"
              else generate(config, "fixture", [ref], transport=transport, validate=operation == "answer"))
    assert len(seen) == 1
    if operation == "answer":
        assert result == ("Supported [chunk:fixture]", [ref])
    else:
        assert result == text


@pytest.mark.parametrize("change", [
    {"status": "incomplete"}, {"status": "failed"}, {"error": {"message": "UNTRUSTED_BODY"}},
    {"output": None}, {"output": []}, {"output": [None]},
    {"output": [{"type": "message", "role": "user", "content": []}]},
    {"output": [{"type": "message", "role": "assistant", "content": [{"type": "refusal", "refusal": "UNTRUSTED_BODY"}]}]},
    {"output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": ["UNTRUSTED_BODY"]}]}]},
])
@pytest.mark.parametrize("operation", ["answer", "plan"])
def test_responses_incomplete_or_nontext_output_never_becomes_answer(tmp_path, change, operation):
    config = replace(provider_settings(tmp_path), ai_protocol="responses")
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={**response_envelope("OK"), **change}))
    with pytest.raises(HTTPException) as error:
        call_provider(config, transport, operation)
    assert_redacted(error, operation)


def test_responses_general_text_excludes_reasoning(tmp_path):
    config = replace(provider_settings(tmp_path), ai_protocol="responses")
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=response_envelope("你好，可以自然提问。")))
    assert generate(config, "你好", [], general=True, transport=transport) == "你好，可以自然提问。"
    with pytest.raises(ValueError):
        provider_content(json.dumps(response_envelope("")), "responses")
