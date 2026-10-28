"""Untrusted provider envelopes fail closed without losing the agent's sources."""
from dataclasses import replace
import json

from fastapi import HTTPException
import httpx
import pytest

from backend.agent_runtime import model_plan
from backend.config import Settings
from backend.rag import generate, validate_answer


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
