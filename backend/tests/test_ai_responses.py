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
        assert "max_output_tokens" not in body
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


@pytest.mark.parametrize("protocol", ["chat_completions", "responses"])
def test_token_truncated_answer_is_rejected_with_actionable_error(tmp_path, protocol):
    config = replace(provider_settings(tmp_path), ai_protocol=protocol)
    envelope = ({"choices":[{"finish_reason":"length", "message":{"content":"UNTRUSTED_PARTIAL"}}]}
                if protocol == "chat_completions" else
                {"status":"incomplete", "incomplete_details":{"reason":"max_output_tokens"}, "output":[]})
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=envelope))
    with pytest.raises(HTTPException) as error:
        generate(config, "fixture", [], general=True, transport=transport)
    assert error.value.detail["code"] == "ai_output_truncated"
    assert "UNTRUSTED_PARTIAL" not in json.dumps(error.value.detail)


@pytest.mark.parametrize("operation", ["answer", "plan", "general"])
@pytest.mark.parametrize("protocol,parameter", [
    ("chat_completions", "max_completion_tokens"),
    ("chat_completions", "max_tokens"),
    ("responses", "max_output_tokens"),
])
@pytest.mark.parametrize("explicit_limit", [None, 32, 256, 65536])
def test_output_limits_are_omitted_by_default_and_explicit_limits_are_not_clamped(
        tmp_path, operation, protocol, parameter, explicit_limit):
    config = replace(provider_settings(tmp_path), ai_protocol=protocol,
                     ai_token_parameter=parameter if protocol == "chat_completions" else "max_completion_tokens")
    if explicit_limit is not None:
        config = replace(config, ai_max_tokens=explicit_limit)
    def provider(request):
        payload = json.loads(request.content)
        token_fields = set(payload) & {"max_tokens", "max_completion_tokens", "max_output_tokens"}
        if explicit_limit is None:
            assert not token_fields
        else:
            assert token_fields == {parameter}
            assert payload[parameter] == explicit_limit
        content = ('{"queries":["computer vision"]}' if operation == "plan" else
                   "Hello" if operation == "general" else '{"answer":"","citations":[]}')
        envelope = (response_envelope(content) if protocol == "responses" else
                    {"choices": [{"message": {"content": content}, "finish_reason": "stop"}]})
        return httpx.Response(200, json=envelope)
    transport = httpx.MockTransport(provider)
    if operation == "general":
        assert generate(config, "hello", [], transport=transport, general=True) == "Hello"
    else:
        call_provider(config, transport, operation)


def test_environment_output_limit_defaults_to_provider_and_accepts_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("AI_MAX_OUTPUT_TOKENS", raising=False)
    assert Settings().ai_max_tokens == Settings.from_env().ai_max_tokens == 0
    monkeypatch.setenv("AI_MAX_OUTPUT_TOKENS", "65536")
    assert Settings.from_env().ai_max_tokens == 65536


@pytest.mark.parametrize("protocol", ["chat_completions", "responses"])
def test_negative_output_limits_fail_before_network(tmp_path, protocol):
    from backend.ai_responses import provider_request
    config = replace(provider_settings(tmp_path), ai_protocol=protocol)
    with pytest.raises(ValueError):
        provider_request(config, [], -1)


@pytest.mark.parametrize("raw", ['before {"queries":[]} after', '```json\n{}\n```\n{}', '```yaml\nqueries: []\n```', '```json\n{}', '```json\n[]\n```'])
def test_model_json_fences_do_not_accept_prose_multiple_objects_or_nonobjects(raw):
    from backend.ai_responses import model_json_object
    with pytest.raises(ValueError):
        model_json_object(raw)


def test_provider_envelopes_still_require_native_json():
    with pytest.raises(ValueError):
        provider_content('```json\n{"choices":[]}\n```', "chat_completions")
