"""Personal providers remain request-scoped; untrusted URLs cannot reach private IPs."""
from dataclasses import replace
import json
import socket

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.config import Settings, make_client
from backend.accounts import Store
from backend.app1 import create_app
from backend.personal_ai import PublicAITransport, personal_settings
from backend.rag import generate
import backend.rag as rag
from test_v2 import login, REAL_ID


@pytest.fixture
def env(tmp_path):
    """Read the explicitly selected corpus; account writes stay in the temporary database."""
    settings = replace(Settings.from_env(), runtime_dir=str(tmp_path), ai_base_url="", ai_model="", ai_api_key="")
    es = make_client(settings)
    assert es.count(index=settings.index)["count"] == 859
    with TestClient(create_app(settings, es)) as api:
        yield api, es, settings, Store(str(tmp_path))
    es.close()


def headers(key="test-only-personal-secret"):
    return {"x-scholarlens-ai-url": "https://provider.example/v1/chat/completions",
            "x-scholarlens-ai-model": "test-model", "x-scholarlens-ai-key": key,
            "x-scholarlens-ai-token-parameter": "max_tokens"}


def test_personal_request_isolation_and_authentication(env, monkeypatch):
    api, _, settings, store = env
    a, _ = login(api, "personal_a")
    b, _ = login(api, "personal_b")
    body = {"question": "magnetic resonance", "paper_ids": [REAL_ID], "mode": "keyword", "top_k": 3}
    assert api.post("/api/ask", headers=headers(), json=body).status_code == 401
    seen = []
    def controlled(config, question, evidence, **kwargs):
        assert config.ai_personal and config.ai_base_url == "https://provider.example/v1"
        seen.append(config.ai_api_key)
        return "Controlled ["+evidence[0]["chunk_id"]+"]", evidence[:1]
    monkeypatch.setattr(rag, "generate", controlled)
    for auth, secret in [(a,"user-a-only-secret"), (b,"user-b-only-secret")]:
        result = api.post("/api/ask", headers={**auth, **headers(secret)}, json=body)
        assert result.status_code == 200, result.text
        assert secret not in result.text and "provider.example" not in result.text
    assert seen == ["user-a-only-secret", "user-b-only-secret"]
    assert not settings.ai_api_key
    assert api.post("/api/ask", headers=b, json=body).status_code == 503
    assert api.get("/api/capabilities").json()["modules"]["ai_qa"]["status"] == "not_configured"
    for url in ["http://provider.example/v1", "https://user:pass@provider.example/v1",
                "https://provider.example/v1?key=secret", "https://provider.example:8000/v1"]:
        result = api.post("/api/ask", headers={**a, **headers(), "x-scholarlens-ai-url": url}, json=body)
        assert result.status_code == 400 and "user-a-only-secret" not in result.text
    assert not any(b"user-a-only-secret" in path.read_bytes() for path in store.root.glob("*.sqlite*"))


@pytest.mark.parametrize("addresses", [["127.0.0.1"], ["169.254.169.254"], ["10.0.0.2"], ["::1"], ["8.8.8.8","192.168.1.2"]])
def test_private_and_mixed_dns_never_connect(addresses, monkeypatch):
    monkeypatch.setattr(socket,"getaddrinfo",lambda *a,**k:[(2,1,6,"",(ip,443)) for ip in addresses])
    transport=PublicAITransport()
    called=[]
    transport.inner.close()
    transport.inner=httpx.MockTransport(lambda request:called.append(request) or httpx.Response(200))
    with httpx.Client(transport=transport) as client, pytest.raises(HTTPException) as error:
        client.get("https://provider.example/v1")
    assert error.value.status_code==400 and not called


def test_dns_is_pinned_with_host_sni_and_no_redirect(monkeypatch):
    lookups=[]
    observed=[]
    def resolve(*a,**k):
        lookups.append(a)
        return [(2,1,6,"",("8.8.8.8" if len(lookups)==1 else "127.0.0.1",443))]
    monkeypatch.setattr(socket,"getaddrinfo",resolve)
    transport=PublicAITransport()
    transport.inner.close()
    def receive(request):
        observed.append(request)
        return httpx.Response(302,headers={"Location":"https://127.0.0.1/private"})
    transport.inner=httpx.MockTransport(receive)
    with httpx.Client(transport=transport,follow_redirects=False) as client:
        assert client.get("https://provider.example/v1").status_code==302
    assert len(lookups)==len(observed)==1
    assert observed[0].url.host=="8.8.8.8"
    assert observed[0].headers["Host"]=="provider.example"
    assert observed[0].extensions["sni_hostname"]=="provider.example"


def test_upstream_errors_do_not_disclose_personal_credentials(tmp_path):
    config=personal_settings(replace(Settings(),runtime_dir=str(tmp_path)),headers(),lambda:None)
    seen=[]
    def reject(request):
        seen.append(request)
        return httpx.Response(401,json={"error":"test-only-personal-secret"})
    with pytest.raises(HTTPException) as error:
        generate(config,"question",[],transport=httpx.MockTransport(reject))
    assert error.value.status_code==502
    assert "test-only-personal-secret" not in json.dumps(error.value.detail)
    assert len(seen)==1


def test_response_endpoint_and_legacy_protocol_normalization():
    config = personal_settings(Settings(), headers(), lambda: None)
    assert config.ai_protocol == "chat_completions"
    config = personal_settings(Settings(), {**headers(), "x-scholarlens-ai-url": "https://provider.example/v1/responses"}, lambda: None)
    assert config.ai_base_url == "https://provider.example/v1" and config.ai_protocol == "responses"
    with pytest.raises(HTTPException):
        personal_settings(Settings(), {**headers(), "x-scholarlens-ai-protocol": "invalid"}, lambda: None)


@pytest.mark.parametrize("status,code", [(401,"ai_authentication_failed"),(403,"ai_authentication_failed"),
                                         (404,"ai_model_unavailable"),(429,"ai_rate_limited")])
def test_explicit_provider_errors_are_not_question_format_errors(tmp_path, status, code):
    config = personal_settings(replace(Settings(), runtime_dir=str(tmp_path)), headers(), lambda: None)
    with pytest.raises(HTTPException) as error:
        generate(config, "你好", [], general=True, transport=httpx.MockTransport(
            lambda request: httpx.Response(status, json={"error": "test-only-personal-secret"})))
    assert error.value.status_code != 401 and error.value.detail["code"] == code
    assert "test-only-personal-secret" not in json.dumps(error.value.detail)


def test_models_and_connection_test_are_authenticated_request_only(tmp_path, monkeypatch):
    class NoRetrieval:
        def close(self): pass
    config = replace(Settings(), runtime_dir=str(tmp_path))
    app = create_app(config, NoRetrieval())
    calls = []
    def provider(request):
        calls.append(request)
        assert request.headers["Authorization"] == "Bearer test-only-personal-secret"
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "available-model"}, {"id": "available-model"}, {"id": {}}]})
        body = json.loads(request.content)
        assert body["max_output_tokens"] == 64 and body["model"] == "available-model"
        return httpx.Response(200, json={"status": "completed", "output": [{"type": "message", "role": "assistant",
            "content": [{"type": "output_text", "text": "OK"}]}]})
    monkeypatch.setattr(rag, "PublicAITransport", lambda: httpx.MockTransport(provider))
    with TestClient(app) as api:
        auth, _ = login(api, "connection_test")
        assert api.get("/api/ai/models", headers=headers()).status_code == 401
        assert api.post("/api/ai/test", headers=headers()).status_code == 401
        assert api.post("/api/ai/test", headers=auth).status_code == 400
        fields = {**auth, **headers(), "x-scholarlens-ai-url": "https://provider.example/v1",
                  "x-scholarlens-ai-model": "", "x-scholarlens-ai-protocol": "responses"}
        result = api.get("/api/ai/models", headers=fields)
        assert result.status_code == 200 and result.json() == {"models": ["available-model"]}
        result = api.post("/api/ai/test", headers={**fields, "x-scholarlens-ai-model": "available-model"})
        assert result.status_code == 200 and result.json() == {"status": "ready", "model": "available-model", "protocol": "responses"}
        assert len(calls) == 2 and not config.ai_api_key
        assert api.get("/api/ai/conversations", headers=auth).json() == []
    with Store(str(tmp_path)).connect() as db:
        assert db.execute("SELECT count(*) FROM conversation_messages").fetchone()[0] == 0
    assert not any(b"test-only-personal-secret" in path.read_bytes() for path in tmp_path.glob("*.sqlite*"))
