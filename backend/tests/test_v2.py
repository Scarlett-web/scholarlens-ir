"""Real ES reads plus explicitly controlled AI/PDF/parser fixtures, never formal data."""

from dataclasses import replace
from io import BytesIO
import json
import uuid
from elasticsearch import Elasticsearch
from fastapi import HTTPException
from fastapi.testclient import TestClient
import httpx
from pypdf import PdfWriter
import pytest
from backend.accounts import Store, password_hash
from backend.app1 import create_app
from backend.chunks import chunks
from backend.config import Settings
from backend.embeddings import Encoder
from backend.rag import generate, validate_answer
from backend.retrieval import rrf
from backend.uploads import tei_to_paper

REAL_ID = "source-sha256:00a0e8b16d0dda799ea25a2f38579c3c203ac076f04d2949c86247f65e98baae"
TEST_XML = b"""<TEI xmlns="http://www.tei-c.org/ns/1.0"><teiHeader><fileDesc><titleStmt><title>Controlled uploaded quasar</title></titleStmt><publicationStmt><date when="2024-06"/></publicationStmt><sourceDesc><biblStruct><analytic><author><persName><forename>Ada</forename><surname>Test</surname></persName><affiliation><orgName>Test University</orgName><address><settlement>Test City</settlement><country>Test Country</country></address></affiliation></author></analytic></biblStruct></sourceDesc></fileDesc><profileDesc><abstract><p>Controlled test abstract.</p></abstract></profileDesc></teiHeader><text><body><div><head>Methods</head><p>Controlled quasar upload text.</p><list><item>List entry.</item></list><formula>x=1</formula></div></body><back><p>Reference must not enter body.</p></back></text></TEI>"""


@pytest.fixture
def env(tmp_path):
    settings = replace(
        Settings(),
        runtime_dir=str(tmp_path),
        uploads_index="scholarlens-uploads-test-" + uuid.uuid4().hex[:10] + "-real",
    )
    es = Elasticsearch(settings.url)
    assert es.count(index=settings.index)["count"] == 859
    app = create_app(settings, es)
    with TestClient(app) as api:
        yield api, es, settings, Store(str(tmp_path))
    es.close()


def login(api, username="test_user"):
    body = {"username": username, "password": "Test-only-password-123!"}
    registered = api.post("/api/auth/register", json=body)
    assert registered.status_code == 201
    result = api.post("/api/auth/login", json=body)
    assert result.status_code == 200
    token = result.json()["access_token"]
    return {"Authorization": "Bearer " + token}, registered.json()


def pdf_bytes():
    out = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    writer.write(out)
    return out.getvalue()


def test_chunks_offsets_coverage_stability_quarantine():
    doc = {"paper_id": "test", "title": "Title", "abstract": "Abstract", "fulltext": "word " * 1000}
    first = chunks(doc)
    second = chunks(doc)
    assert first == second and len({c["chunk_id"] for c in first}) == len(first)
    body = [c for c in first if c["field"] == "fulltext"]
    assert body[0]["offset_start"] == 0 and body[-1]["offset_end"] == len(doc["fulltext"])
    assert all(a["offset_end"] >= b["offset_start"] for a, b in zip(body, body[1:]))
    for c in first:
        assert c["text"] == doc[c["field"]][c["offset_start"] : c["offset_end"]]
    assert not any(
        c["field"] == "fulltext"
        for c in chunks({**doc, "errors": ["unreadable_characters_in_fulltext"]})
    )


def test_rrf_uses_ranks_and_deduplicates():
    result = rrf(["a", "b", "b"], ["b", "c"])
    assert result[0][0] == "b" and len(result) == 3
    assert result[0][1] == pytest.approx(1 / 62 + 1 / 61)


def test_actual_encoder_is_normalized_and_semantic():
    enc = Encoder(Settings().model_dir)
    a, b, c = enc.encode(
        ["brain MRI imaging", "magnetic resonance brain scan", "soil gardening and flowers"]
    )
    assert len(a) == 384 and sum(x * x for x in a) == pytest.approx(1, abs=1e-5)
    assert sum(x * y for x, y in zip(a, b)) > sum(x * y for x, y in zip(a, c))


def test_suggest_discover_and_caps(env):
    api, *_ = env
    stats = api.get("/api/stats")
    assert stats.json()["indexed"] == 859
    suggestions = api.get("/api/suggest", params={"q": "magnet", "limit": 20}).json()["suggestions"]
    assert any(s["paper_id"] == REAL_ID for s in suggestions)
    assert len({s["text"].casefold() for s in suggestions}) == len(suggestions)
    assert api.get("/api/suggest?q=").json()["suggestions"] == []
    assert api.get("/api/suggest?q=%25%5B%5D").json()["suggestions"] == []
    assert api.get("/api/suggest?q=x&limit=21").status_code == 400
    discovered = api.get("/api/discover?limit=3").json()
    assert discovered["papers"] == 859 and len(discovered["recommendations"]) == 3
    assert discovered["years"] and discovered["status"] == "real"
    caps = api.get("/api/capabilities").json()["modules"]
    assert caps["keyword_search"]["status"] == "ready"
    assert caps["ai_qa"]["status"] == "not_configured"
    assert caps["pdf_preview"]["status"] == "not_configured"


def test_auth_password_sessions_logout_and_unique(env):
    api, _, _, store = env
    headers, user = login(api)
    assert api.get("/api/auth/me", headers=headers).json() == user
    assert api.get("/api/auth/me").status_code == 401
    assert (
        api.post(
            "/api/auth/register", json={"username": "TEST_USER", "password": "different-pass-123"}
        ).status_code
        == 409
    )
    assert (
        api.post("/api/auth/register", json={"username": "new", "password": "short"}).status_code
        == 400
    )
    with store.connect() as db:
        saved = db.execute("SELECT * FROM users").fetchone()
        session = db.execute("SELECT * FROM sessions").fetchone()
        assert saved["password_hash"] != "Test-only-password-123!"
        assert session["token_hash"] not in headers["Authorization"]
        assert saved["password_hash"] == password_hash("Test-only-password-123!", saved["salt"])
    assert api.post("/api/auth/logout", headers=headers).json()["logged_out"]
    assert api.get("/api/auth/me", headers=headers).status_code == 401


def test_login_lockout(env):
    api, *_ = env
    login(api)
    for _ in range(5):
        assert (
            api.post(
                "/api/auth/login", json={"username": "test_user", "password": "wrong-password-123"}
            ).status_code
            == 401
        )
    assert (
        api.post(
            "/api/auth/login", json={"username": "test_user", "password": "Test-only-password-123!"}
        ).status_code
        == 429
    )


def test_favorites_history_isolation_and_reopen(env):
    api, es, settings, store = env
    a, _ = login(api, "user_a")
    b, _ = login(api, "user_b")
    assert api.put("/api/me/favorites/" + REAL_ID, headers=a).json()["is_favorite"]
    assert not api.get("/api/me/favorites/" + REAL_ID, headers=b).json()["is_favorite"]
    assert api.get("/api/me/favorites", headers=b).json()["total"] == 0
    record = api.post("/api/me/history", json={"q": "magnetic", "field": "title"}, headers=a).json()
    assert api.get("/api/me/history", headers=b).json()["total"] == 0
    assert api.get("/api/me/history?page=" + str(10**30), headers=a).status_code == 400
    assert api.get("/api/me/favorites?page=" + str(10**30), headers=a).status_code == 400
    assert api.delete("/api/me/history/" + str(record["id"]), headers=b).status_code == 404
    with TestClient(create_app(settings, es)) as restarted:
        assert restarted.get("/api/me/favorites", headers=a).json()["total"] == 1
        assert restarted.get("/api/me/history", headers=a).json()["total"] == 1
    assert api.delete("/api/me/favorites/" + REAL_ID, headers=a).json()["is_favorite"] is False
    assert api.delete("/api/me/history", headers=a).json()["cleared"]
    assert api.get("/api/me/history", headers=a).json()["total"] == 0
    assert api.put("/api/me/favorites/not-a-paper", headers=a).status_code == 404
    assert api.post("/api/me/history", json={"q": "  "}, headers=a).status_code == 400


def test_ai_not_configured_and_real_lexical_evidence(env):
    api, *_ = env
    r = api.post("/api/ask", json={"question": "What is inverse imaging?", "paper_ids": [REAL_ID]})
    assert r.status_code == 503 and r.json()["error"]["code"] == "ai_not_configured"
    assert api.post("/api/ask", json={"question": " "}).status_code == 400
    refs = api.post(
        "/api/evidence",
        json={
            "question": "magnetic resonance imaging",
            "paper_ids": [REAL_ID],
            "mode": "keyword",
            "top_k": 3,
        },
    )
    assert refs.status_code == 200 and refs.json()
    doc = api.get("/api/papers/" + REAL_ID).json()
    for c in refs.json():
        field, _, span = c["locator"].split(":")
        start, end = map(int, span.split("-"))
        assert c["paper_id"] == REAL_ID and doc[field][start:end] == c["quote"]
    assert (
        api.post(
            "/api/evidence", json={"question": "zzzscholarlensunknown", "mode": "keyword"}
        ).json()
        == []
    )
    assert (
        api.post(
            "/api/evidence", json={"question": "MRI", "paper_ids": ["not-found"], "mode": "keyword"}
        ).status_code
        == 404
    )


def citation():
    return {
        "paper_id": "controlled",
        "paper_title": "Controlled fixture",
        "chunk_id": "chunk:" + "a" * 64,
        "quote": "The controlled evidence states that MRI measures brain signals.",
        "locator": "abstract:chars:0-70",
        "relevance_score": 1.0,
    }


def test_ai_adapter_controlled_response_and_citations():
    c = citation()

    def respond(request):
        body = json.loads(request.content)
        assert (
            body["max_completion_tokens"] == 800
            and request.headers["Authorization"] == "Bearer test-only"
        )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "answer": "MRI measures brain signals. [" + c["chunk_id"] + "]",
                                    "citations": [
                                        {
                                            "chunk_id": c["chunk_id"],
                                            "quote": "MRI measures brain signals.",
                                        }
                                    ],
                                }
                            )
                        }
                    }
                ]
            },
        )

    settings = replace(
        Settings(),
        ai_api_key="test-only",
        ai_base_url="http://controlled.invalid/v1",
        ai_model="controlled-model",
    )
    answer, refs = generate(settings, "What does MRI measure?", [c], httpx.MockTransport(respond))
    assert "brain" in answer and refs[0]["quote"] == "MRI measures brain signals."
    bad = {
        "answer": "unsupported [" + c["chunk_id"] + "]",
        "citations": [{"chunk_id": c["chunk_id"], "quote": "a fabricated quotation"}],
    }
    with pytest.raises(HTTPException):
        validate_answer(json.dumps(bad), [c])
    bad["citations"][0]["quote"] = "MRI measures brain signals."
    bad["answer"] += " [chunk:fake]"
    with pytest.raises(HTTPException):
        validate_answer(json.dumps(bad), [c])


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "ai_authentication_failed"),
        (429, "ai_rate_limited"),
        (500, "ai_upstream_error"),
        (400, "ai_upstream_error"),
    ],
)
def test_ai_provider_errors_are_redacted(status, code):
    settings = replace(
        Settings(),
        ai_api_key="test-secret",
        ai_base_url="http://controlled.invalid/v1",
        ai_model="controlled-model",
    )
    with pytest.raises(HTTPException) as e:
        generate(
            settings,
            "question",
            [citation()],
            httpx.MockTransport(lambda _: httpx.Response(status, text="sensitive upstream body")),
        )
    assert (
        e.value.detail["code"] == code
        and "sensitive" not in str(e.value.detail)
        and "test-secret" not in str(e.value.detail)
    )


def test_body_paging_and_pdf_unavailable(env):
    api, *_ = env
    full = api.get("/api/papers/" + REAL_ID).json()
    short = api.get("/api/papers/" + REAL_ID, params={"include_fulltext": False}).json()
    assert short["fulltext"] == "" and short["source_info"]["fulltext_characters"] == len(
        full["fulltext"]
    )
    part = api.get("/api/papers/" + REAL_ID + "/content?offset=20&limit=100").json()
    assert part["text"] == full["fulltext"][20:120]
    assert api.get("/api/papers/" + REAL_ID + "/content?offset=-1").status_code == 400
    assert api.get("/api/papers/" + REAL_ID + "/pdf").json()["error"]["code"] == "pdf_not_available"


def test_upload_review_permissions_missing_parser_and_bad_files(env):
    api, _, _, store = env
    user, _ = login(api)
    other, _ = login(api, "other_user")
    assert (
        api.post(
            "/api/uploads", files={"file": ("test.pdf", pdf_bytes(), "application/pdf")}
        ).status_code
        == 401
    )
    for name, data in [
        ("not.txt", b"abc"),
        ("bad.pdf", b"not pdf"),
        ("broken.pdf", b"%PDF-1.4\ninvalid"),
    ]:
        assert (
            api.post(
                "/api/uploads", headers=user, files={"file": (name, data, "application/pdf")}
            ).status_code
            == 400
        )
    result = api.post(
        "/api/uploads",
        headers=user,
        files={"file": ("controlled.pdf", pdf_bytes(), "application/pdf")},
    )
    assert result.status_code == 201, result.text
    item = result.json()
    assert item["status"] == "pending" and "stored_name" not in item
    assert api.get("/api/uploads/" + item["id"], headers=other).status_code == 404
    assert (
        api.post(
            "/api/admin/uploads/" + item["id"] + "/review",
            headers=user,
            json={"decision": "approve"},
        ).status_code
        == 403
    )
    with store.connect() as db:
        db.execute("UPDATE users SET role='admin' WHERE username='other_user'")
    assert (
        api.post(
            "/api/admin/uploads/" + item["id"] + "/review",
            headers=other,
            json={"decision": "approve"},
        ).json()["status"]
        == "approved"
    )
    r = api.post("/api/admin/uploads/" + item["id"] + "/process", headers=other)
    # Without GROBID, actual text extraction is attempted. This blank fixture requires OCR.
    assert r.status_code == 202
    state = api.get("/api/uploads/" + item["id"], headers=user).json()
    assert state["status"] == "failed" and state["reason"] == "pdf_requires_ocr"
    assert (
        api.post(
            "/api/uploads",
            headers=user,
            files={"file": ("controlled.pdf", pdf_bytes(), "application/pdf")},
        ).status_code
        == 409
    )


def test_controlled_parse_incremental_index_and_pdf_range(env, monkeypatch):
    api, es, settings, store = env
    headers, _ = login(api)
    with store.connect() as db:
        db.execute("UPDATE users SET role='admin' WHERE username='test_user'")
    settings = replace(settings, grobid_url="http://controlled.invalid")
    monkeypatch.setattr("backend.uploads.call_grobid", lambda *_: TEST_XML)
    with TestClient(create_app(settings, es)) as client:
        item = client.post(
            "/api/uploads",
            headers=headers,
            files={"file": ("controlled.pdf", pdf_bytes(), "application/pdf")},
        ).json()
        route = "/api/admin/uploads/" + item["id"]
        assert (
            client.post(
                route + "/review", headers=headers, json={"decision": "approve"}
            ).status_code
            == 200
        )
        response = client.post(route + "/process", headers=headers)
        assert response.status_code == 202, response.text
        record = client.get("/api/uploads/" + item["id"], headers=headers).json()
        assert record["status"] == "indexed", record
        paper = record["paper_id"]
        detail = client.get("/api/papers/" + paper).json()
        assert (
            detail["title"] == "Controlled uploaded quasar"
            and detail["year"] == 2024
            and detail["date"] == ""
        )
        assert "Reference must not" not in detail["fulltext"]
        assert detail["authors"] == ["Ada Test"] and detail["pdf_available"]
        hits = client.get("/api/search?q=controlled&field=title").json()
        assert paper in [r["paper_id"] for r in hits["results"]]
        full = client.get("/api/papers/" + paper + "/pdf")
        part = client.get("/api/papers/" + paper + "/pdf", headers={"Range": "bytes=0-4"})
        assert full.status_code == 200 and full.headers["content-type"] == "application/pdf"
        assert part.status_code == 206 and part.content == b"%PDF-"
        invalid = client.get("/api/papers/" + paper + "/pdf", headers={"Range": "bytes=99999999-"})
        assert (
            invalid.status_code == 416
            and invalid.json()["error"]["code"] == "range_not_satisfiable"
        )
        invalid = client.get("/api/papers/" + paper + "/pdf", headers={"Range": "garbage"})
        assert invalid.status_code == 400 and invalid.json()["error"]["code"] == "invalid_parameter"
        assert es.count(index=settings.index)["count"] == 859
        assert client.get("/api/stats").json()["indexed"] == 859


def test_upload_tei_structures_and_entity_rejection():
    doc = tei_to_paper(TEST_XML, "0" * 64, "controlled.pdf", "uploads/files/controlled.pdf", 1)
    assert doc["authors"] == ["Ada Test"] and doc["address"] == ["Test City Test Country"]
    assert "List entry." in doc["fulltext"] and "x=1" in doc["fulltext"]
    with pytest.raises(ValueError):
        tei_to_paper(b'<!DOCTYPE x [<!ENTITY z "x">]><TEI/>', "0" * 64, "x", "x", 1)


def test_pdf_manifest_migration_hash_and_boundary(tmp_path):
    import csv
    import hashlib
    from backend.pdf_access1 import resolve_document_pdf

    content = pdf_bytes()
    (tmp_path / "controlled.pdf").write_bytes(content)
    manifest = tmp_path / "manifest.csv"

    def write_row(name, sha):
        with manifest.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["paper_id", "source_file", "pdf_sha256"])
            writer.writeheader()
            writer.writerow({"paper_id": "controlled-id", "source_file": name, "pdf_sha256": sha})

    write_row("controlled.pdf", hashlib.sha256(content).hexdigest())
    settings = replace(Settings(), pdf_root=str(tmp_path), pdf_manifest_path=str(manifest))
    doc = {
        "paper_id": "controlled-id",
        "source_file": "controlled.pdf",
        "pdf_path": "old/machine/path.pdf",
    }
    assert resolve_document_pdf(doc, settings) == (tmp_path / "controlled.pdf").resolve()
    write_row("controlled.pdf", "0" * 64)
    assert resolve_document_pdf(doc, settings) is None
    write_row("../controlled.pdf", hashlib.sha256(content).hexdigest())
    assert resolve_document_pdf({**doc, "source_file": "../controlled.pdf"}, settings) is None


def test_upload_request_limits_and_unauthorized_body(env):
    api, *_ = env
    headers, _ = login(api)
    r = api.post(
        "/api/uploads", headers={**headers, "Content-Length": str(22 * 1024 * 1024)}, content=b"x"
    )
    assert r.status_code == 413 and r.json()["error"]["code"] == "file_too_large"
    r = api.post("/api/uploads", headers={"Content-Length": str(22 * 1024 * 1024)}, content=b"x")
    assert r.status_code == 401


def test_ai_timeout_invalid_json_and_no_evidence():
    settings = replace(
        Settings(),
        ai_api_key="test-only",
        ai_base_url="http://controlled.invalid/v1",
        ai_model="controlled",
    )

    def timeout(_):
        raise httpx.ReadTimeout("controlled timeout")

    with pytest.raises(HTTPException) as e:
        generate(settings, "q", [citation()], httpx.MockTransport(timeout))
    assert e.value.status_code == 504 and e.value.detail["code"] == "ai_timeout"
    with pytest.raises(HTTPException) as e:
        generate(
            settings,
            "q",
            [citation()],
            httpx.MockTransport(
                lambda _: httpx.Response(
                    200, json={"choices": [{"message": {"content": "invalid JSON"}}]}
                )
            ),
        )
    assert e.value.detail["code"] == "ai_invalid_response"
    assert validate_answer('{"answer":"","citations":[]}', []) == ("", [])


def test_complete_rag_api_with_controlled_provider_and_real_evidence(env, monkeypatch):
    api, es, settings, _ = env
    configured = replace(
        settings,
        ai_api_key="controlled-key",
        ai_base_url="http://controlled.invalid/v1",
        ai_model="controlled",
    )

    def provider(request):
        prompt = json.loads(json.loads(request.content)["messages"][1]["content"])
        evidence = prompt["evidence"][0]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "answer": "The retrieved paper reports this finding. ["
                                    + evidence["chunk_id"]
                                    + "]",
                                    "citations": [
                                        {
                                            "chunk_id": evidence["chunk_id"],
                                            "quote": evidence["quote"][:80],
                                        }
                                    ],
                                }
                            )
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr(
        "backend.rag.generate", lambda s, q, e: generate(s, q, e, httpx.MockTransport(provider))
    )
    with TestClient(create_app(configured, es)) as client:
        body = {"question": "magnetic resonance imaging", "mode": "keyword", "paper_ids": [REAL_ID]}
        r = client.post("/api/ask", json=body)
        assert r.status_code == 200 and r.json()["evidence_status"] == "sufficient", r.text
        assert r.json()["citations"][0]["paper_id"] == REAL_ID
        r = client.post("/api/ask", json={**body, "question": "zzunknownxyz"})
        assert (
            r.json()["evidence_status"] == "insufficient_evidence"
            and r.json()["model"]["status"] == "not_called"
        )
        r = client.post("/api/ask", json={**body, "paper_ids": ["unknown"]})
        assert r.status_code == 404
        assert (
            client.get("/api/capabilities").json()["modules"]["ai_qa"]["status"]
            == "dependency_unavailable"
        )


def test_openapi_models_and_cors_allowlist(env):
    api, es, settings, _ = env
    schema = api.get("/openapi.json").json()
    required = [
        "/api/search",
        "/api/stats",
        "/api/ask",
        "/api/evidence",
        "/api/suggest",
        "/api/discover",
        "/api/capabilities",
        "/api/auth/login",
        "/api/me/favorites",
        "/api/me/history",
        "/api/uploads",
    ]
    assert set(required) <= set(schema["paths"])
    for route in required:
        for operation in schema["paths"][route].values():
            assert "422" not in operation.get("responses", {})
    assert schema["paths"]["/api/auth/login"]["post"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["$ref"].endswith("LoginResponse")
    with TestClient(
        create_app(replace(settings, cors_origins="http://localhost:5173"), es)
    ) as client:
        allowed = client.options(
            "/api/stats",
            headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
        )
        blocked = client.options(
            "/api/stats",
            headers={"Origin": "http://unlisted.invalid", "Access-Control-Request-Method": "GET"},
        )
        assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
        assert "access-control-allow-origin" not in blocked.headers


def test_vector_checkpoint_retry_and_resume_preserves_base(env, tmp_path, monkeypatch):
    import backend.vector_index as module
    from backend.import_jsonl import import_records, load_jsonl
    from filelock import FileLock, Timeout

    api, es, settings, _ = env
    row = es.get(index=settings.index, id=REAL_ID)["_source"]
    row.pop("date_value", None)
    # Keep real metadata but use the real title alone for a small independent resume test.
    row["abstract"] = ""
    row["fulltext"] = ""
    source = tmp_path / "selected-real-title.jsonl"
    source.write_text(json.dumps(row) + "\n", encoding="utf-8")
    docs, metadata = load_jsonl(source, "real")
    alias = "scholarlens-v2-resume-" + uuid.uuid4().hex[:8] + "-real"
    import_records(es, alias, docs, metadata)
    config = replace(
        settings, index=alias, vector_index="scholarlens-vectors-test-" + uuid.uuid4().hex[:8]
    )
    state = tmp_path / "state.json"
    original = module.bulk
    calls = []

    def crash_after_ack(*args, **kwargs):
        original(*args, **kwargs)
        calls.append(True)
        raise RuntimeError("controlled crash after bulk acknowledgment, before checkpoint")

    monkeypatch.setattr(module, "bulk", crash_after_ack)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    with pytest.raises(RuntimeError):
        module.build(config, state, batch_size=1)
    checkpoint = json.loads(state.read_text())
    assert checkpoint["completed"] == 0 and not es.indices.exists_alias(name=config.vector_index)
    monkeypatch.setattr(module, "bulk", original)
    completed = module.build(config, state, batch_size=1)
    assert completed["status"] == "ready" and es.count(index=config.vector_index)["count"] == 1
    repeated = module.build(config, state, batch_size=1)
    assert repeated == completed
    with FileLock(str(state) + ".lock"):
        # A different lock object cannot concurrently build the same checkpoint.
        with pytest.raises(Timeout):
            module.build(config, state)
    with pytest.raises(ValueError):
        module.build(replace(config, vector_index=settings.index), state)
    assert es.count(index=settings.index)["count"] == 859


def test_upload_rejection_failed_parse_retry_and_unreviewed_guard(env, monkeypatch):
    api, es, settings, store = env
    headers, _ = login(api)
    with store.connect() as db:
        db.execute("UPDATE users SET role='admin' WHERE username='test_user'")
    item = api.post(
        "/api/uploads",
        headers=headers,
        files={"file": ("controlled.pdf", pdf_bytes(), "application/pdf")},
    ).json()
    route = "/api/admin/uploads/" + item["id"]
    assert api.post(route + "/process", headers=headers).status_code == 409
    assert (
        api.post(
            route + "/review",
            headers=headers,
            json={"decision": "reject", "reason": "controlled test rejection"},
        ).json()["status"]
        == "rejected"
    )
    assert api.post(route + "/process", headers=headers).status_code == 409
    assert not es.indices.exists_alias(name=settings.uploads_index)
    # A second, separate user can upload the same fixture; it still requires review.
    second, _ = login(api, "other_user")
    item = api.post(
        "/api/uploads",
        headers=second,
        files={"file": ("controlled.pdf", pdf_bytes(), "application/pdf")},
    ).json()
    route = "/api/admin/uploads/" + item["id"]
    assert (
        api.post(route + "/review", headers=headers, json={"decision": "approve"}).status_code
        == 200
    )

    def missing_parser(*_):
        raise httpx.ConnectError("controlled unavailable parser")

    monkeypatch.setattr("backend.uploads.call_grobid", missing_parser)
    with TestClient(
        create_app(replace(settings, grobid_url="http://controlled.invalid"), es)
    ) as configured:
        assert configured.post(route + "/process", headers=headers).status_code == 202
        state = configured.get("/api/uploads/" + item["id"], headers=second).json()
        assert state["status"] == "failed" and state["reason"] == "parse_dependency_unavailable"
        assert not es.indices.exists_alias(name=settings.uploads_index)
        monkeypatch.setattr("backend.uploads.call_grobid", lambda *_: TEST_XML)
        assert configured.post(route + "/process", headers=headers).status_code == 202
        state = configured.get("/api/uploads/" + item["id"], headers=second).json()
        assert state["status"] == "indexed" and state["attempts"] == 2
        assert configured.post(route + "/process", headers=headers).status_code == 409
        assert es.count(index=settings.index)["count"] == 859


def test_upload_block_boundaries_and_empty_parse():
    doc = tei_to_paper(TEST_XML, "0" * 64, "controlled.pdf", "controlled.pdf", 1)
    assert "Methods Controlled" in doc["fulltext"]
    assert "text. List entry. x=1" in doc["fulltext"]
    with pytest.raises(ValueError):
        tei_to_paper(b'<TEI xmlns="http://www.tei-c.org/ns/1.0"/>', "0" * 64, "x", "x", 1)


def test_chunk_pagination_without_vector_dependency(env):
    api, *_ = env
    parts = api.get("/api/papers/" + REAL_ID + "/chunks?page=1&page_size=2").json()
    assert parts["total"] > 2 and len(parts["results"]) == 2
    doc = api.get("/api/papers/" + REAL_ID).json()
    for part in parts["results"]:
        assert doc[part["field"]][part["offset_start"] : part["offset_end"]] == part["text"]
    assert api.get("/api/chunks/not-a-chunk").status_code == 400


@pytest.mark.skipif(__import__("os").name != "nt", reason="Windows file sharing behavior")
def test_checkpoint_retries_while_windows_reader_holds_file(tmp_path):
    import threading
    from backend.vector_index import atomic_state

    path = tmp_path / "state.json"
    path.write_text('{"old":true}', encoding="utf-8")
    opened = path.open("rb")
    timer = threading.Timer(0.2, opened.close)
    timer.start()
    try:
        atomic_state(path, {"completed": 8})
        assert json.loads(path.read_text()) == {"completed": 8}
    finally:
        opened.close()
        timer.join()


def test_real_selected_metadata_vector_and_rrf_endpoints(env, tmp_path):
    from backend.vector_index import build
    from backend.import_jsonl import import_records, load_jsonl

    api, es, settings, _ = env
    ids = [
        REAL_ID,
        "source-sha256:e33df84457cadc564e926ec0f4f62cf54e89ce95fcf97afbdfefe9fad109bfa3",
        "source-sha256:04873cf9e14a45fc45bd6ad437f2dae275538bd3b16e3b9c0f315ad35a769efb",
    ]
    records = []
    for paper in ids:
        doc = es.get(index=settings.index, id=paper)["_source"]
        doc.pop("date_value", None)
        doc["fulltext"] = ""
        records.append(doc)
    source = tmp_path / "selected-real-metadata.jsonl"
    source.write_text("".join(json.dumps(d) + "\n" for d in records), encoding="utf-8")
    docs, meta = load_jsonl(source, "real")
    alias = "scholarlens-selected-" + uuid.uuid4().hex[:8] + "-real"
    import_records(es, alias, docs, meta)
    chosen = replace(
        settings, index=alias, vector_index="scholarlens-vectors-test-" + uuid.uuid4().hex[:8]
    )
    report = build(chosen, tmp_path / "selected-vector-state.json")
    assert report["identity"]["papers"] == 3
    with TestClient(create_app(chosen, es)) as client:
        for mode in ("semantic", "hybrid"):
            response = client.get(
                "/api/search",
                params={"q": "brain magnetic resonance imaging", "mode": mode, "field": "title"},
            )
            assert response.status_code == 200, response.text
            assert response.json()["results"][0]["paper_id"] == REAL_ID
            assert response.json()["results"][0]["score"] > 0
            refs = client.post(
                "/api/evidence",
                json={
                    "question": "magnetic resonance brain imaging",
                    "paper_ids": [REAL_ID],
                    "mode": mode,
                    "top_k": 3,
                },
            )
            assert refs.status_code == 200 and refs.json(), refs.text
            chunk = refs.json()[0]["chunk_id"]
            assert client.get("/api/chunks/" + chunk).json()["paper_id"] == REAL_ID
        assert (
            client.get("/api/capabilities").json()["modules"]["semantic_search"]["status"]
            == "ready"
        )
    assert es.count(index=settings.index)["count"] == 859


def test_semantic_invalid_parameters_before_dependency(tmp_path):
    class NoExternalCalls:
        pass

    with TestClient(
        create_app(replace(Settings(), runtime_dir=str(tmp_path)), NoExternalCalls())
    ) as api:
        assert api.get("/api/search?q=test&mode=semantic&field=authors").status_code == 400
        assert api.get("/api/search?q=test&mode=semantic&page=60&page_size=20").status_code == 400
