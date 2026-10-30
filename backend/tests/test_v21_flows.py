"""Security, persistence, conversion and grounded AI flows for the V2.1 APIs."""
# ruff: noqa: F811 -- imported pytest fixtures are injected into test parameters.

from dataclasses import replace
from io import BytesIO
import json
import sqlite3

from fastapi.testclient import TestClient
from PIL import Image
import httpx
import pytest

from backend.accounts import Store
from backend.app1 import create_app
from backend.db_migrations import restore
from backend.docx_convert import convert_pdf_to_docx
from backend.tests.test_v21 import v21, token, pdf_bytes, REAL_ID  # noqa: F401

OTHER_ID = "source-sha256:e33df84457cadc564e926ec0f4f62cf54e89ce95fcf97afbdfefe9fad109bfa3"


def test_user_deactivation_and_review_record_archival(v21):
    api, _, settings, runtime = v21
    a = token(api)
    b = token(api, "operator")
    with Store(settings.runtime_dir).connect() as db:
        db.execute("UPDATE users SET role='admin' WHERE id=2")
    item = api.post(
        "/api/uploads", headers=a, files={"file": ("retained.pdf", pdf_bytes(), "application/pdf")}
    ).json()
    archive = api.delete("/api/admin/uploads/" + item["id"], headers=b)
    assert archive.status_code == 200 and archive.json()["source_preserved"]
    assert api.get("/api/admin/uploads", headers=b).json()["total"] == 0
    assert api.get("/api/uploads/" + item["id"], headers=a).json()["archived"]
    assert len(list((runtime / "uploads/files").glob("*.pdf"))) == 1
    assert api.post("/api/admin/uploads/" + item["id"] + "/process", headers=b).status_code == 409
    wrong = api.post(
        "/api/auth/deactivate",
        headers=a,
        json={"username": "v21_user", "password": "incorrect-password"},
    )
    assert wrong.status_code == 401
    result = api.post(
        "/api/auth/deactivate",
        headers=a,
        json={"username": "v21_user", "password": "V21-strong-password-123!"},
    )
    assert result.status_code == 200 and api.get("/api/auth/me", headers=a).status_code == 401
    with Store(settings.runtime_dir).connect() as db:
        assert db.execute("SELECT count(*) FROM users").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM uploads").fetchone()[0] == 1


def test_verified_email_recovery_rejects_reuse_and_revokes_sessions(v21, monkeypatch):
    api, _, settings, _ = v21
    headers = token(api)
    api.patch("/api/me/profile", headers=headers, json={"email": "Owner@Example.com"})
    monkeypatch.setenv("EMAIL_BASE_URL", "http://mail-fixture.invalid/send")
    sent = []

    def mail(url, **kwargs):
        sent.append(kwargs["json"])
        return httpx.Response(202, request=httpx.Request("POST", url))

    monkeypatch.setattr("backend.email_codes.httpx.post", mail)
    assert (
        api.post(
            "/api/me/email/request", headers=headers, json={"email": "owner@example.com"}
        ).status_code
        == 200
    )
    assert (
        api.post(
            "/api/me/email/request", headers=headers, json={"email": "owner@example.com"}
        ).status_code
        == 429
    )
    assert (
        api.post(
            "/api/me/email/verify",
            headers=headers,
            json={"email": "owner@example.com", "code": sent[-1]["code"]},
        ).status_code
        == 200
    )
    assert api.get("/api/me/profile", headers=headers).json()["email_verified"]
    assert (
        api.post(
            "/api/auth/password-reset/request", json={"email": "owner@example.com"}
        ).status_code
        == 200
    )
    reset = {
        "email": "owner@example.com",
        "code": sent[-1]["code"],
        "new_password": "Replacement-password-2026!",
    }
    assert api.post("/api/auth/password-reset/verify", json=reset).status_code == 200
    assert api.post("/api/auth/password-reset/verify", json=reset).status_code == 400
    assert api.get("/api/auth/me", headers=headers).status_code == 401
    assert (
        api.post(
            "/api/auth/login",
            json={"username": "v21_user", "password": "Replacement-password-2026!"},
        ).status_code
        == 200
    )
    with Store(settings.runtime_dir).connect() as db:
        rows = db.execute("SELECT * FROM email_codes").fetchall()
        assert all(r["code_hash"] != m["code"] for r in rows for m in sent)


def test_email_codes_expiry_attempts_scope_and_unverified_mail(v21, monkeypatch):
    api, _, settings, _ = v21
    a = token(api)
    b = token(api, "second_user")
    api.patch("/api/me/profile", headers=a, json={"email": "owner@example.com"})
    monkeypatch.setenv("EMAIL_BASE_URL", "http://mail-fixture.invalid/send")
    sent = []
    monkeypatch.setattr(
        "backend.email_codes.httpx.post",
        lambda url, **kw: (
            sent.append(kw["json"]) or httpx.Response(200, request=httpx.Request("POST", url))
        ),
    )
    assert (
        api.post(
            "/api/auth/password-reset/request", json={"email": "owner@example.com"}
        ).status_code
        == 200
    )
    assert not sent  # Unverified self-entered email must not enable account recovery.
    api.post("/api/me/email/request", headers=a, json={"email": "owner@example.com"})
    correct = sent[-1]["code"]
    assert (
        api.post(
            "/api/me/email/verify", headers=b, json={"email": "owner@example.com", "code": correct}
        ).status_code
        == 400
    )
    for _ in range(5):
        assert (
            api.post(
                "/api/me/email/verify",
                headers=a,
                json={
                    "email": "owner@example.com",
                    "code": "00000000" if correct != "00000000" else "11111111",
                },
            ).status_code
            == 400
        )
    assert (
        api.post(
            "/api/me/email/verify", headers=a, json={"email": "owner@example.com", "code": correct}
        ).status_code
        == 400
    )
    with Store(settings.runtime_dir).connect() as db:
        db.execute("UPDATE email_codes SET expires=0,attempts=0 WHERE purpose='verify_email'")
    assert (
        api.post(
            "/api/me/email/verify", headers=a, json={"email": "owner@example.com", "code": correct}
        ).status_code
        == 400
    )


def test_failed_mail_provider_is_not_reported_sent(v21, monkeypatch):
    api, _, _, _ = v21
    headers = token(api)
    api.patch("/api/me/profile", headers=headers, json={"email": "owner@example.com"})
    monkeypatch.setenv("EMAIL_BASE_URL", "http://mail-fixture.invalid/send")
    monkeypatch.setattr(
        "backend.email_codes.httpx.post",
        lambda url, **kw: httpx.Response(500, request=httpx.Request("POST", url)),
    )
    r = api.post("/api/me/email/request", headers=headers, json={"email": "owner@example.com"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "email_service_unavailable"


def test_profile_avatar_identity_and_private_access(v21):
    api, _, _, _ = v21
    a = token(api)
    b = token(api, "second_user")
    assert api.patch("/api/me/profile", headers=a, json={"username": None}).status_code == 400
    assert api.patch("/api/me/profile", headers=a, json={"email": "bad mail"}).status_code == 400
    assert (
        api.patch("/api/me/profile", headers=a, json={"username": "second_user"}).status_code == 409
    )
    renamed = api.patch(
        "/api/me/profile",
        headers=a,
        json={"username": "renamed_user", "display_name": "Display name"},
    )
    assert renamed.status_code == 200 and renamed.json()["username"] == "renamed_user"
    assert (
        api.post(
            "/api/me/avatar",
            headers=a,
            files={"file": ("bad.png", b"\x89PNG\r\n\x1a\ninvalid", "image/png")},
        ).status_code
        == 400
    )
    data = BytesIO()
    Image.new("RGB", (20, 20), (40, 90, 130)).save(data, format="PNG")
    assert (
        api.post(
            "/api/me/avatar",
            headers=a,
            files={"file": ("avatar.png", data.getvalue(), "image/png")},
        ).status_code
        == 200
    )
    assert api.get("/api/me/avatar", headers=a).status_code == 200
    assert api.get("/api/me/avatar", headers=b).status_code == 404
    assert api.get("/api/me/avatar").status_code == 401
    bad = api.post(
        "/api/auth/password",
        headers=a,
        json={"current_password": "incorrect", "new_password": "Different-password-123!"},
    )
    assert bad.status_code == 401


def test_folder_history_persistence_and_user_isolation(v21):
    api, es, settings, _ = v21
    a = token(api)
    b = token(api, "second_user")
    folder = api.post("/api/me/favorite-folders", headers=a, json={"name": "Methods"}).json()
    assert api.post("/api/me/favorite-folders", headers=a, json={"name": "  "}).status_code == 400
    assert (
        api.post("/api/me/favorite-folders", headers=a, json={"name": "Methods"}).status_code == 409
    )
    route = f"/api/me/favorite-folders/{folder['id']}"
    assert api.patch(route, headers=b, json={"name": "stolen"}).status_code == 404
    api.put(route + "/papers", headers=a, json={"paper_id": REAL_ID})
    api.post("/api/me/browsing-history", headers=a, json={"paper_id": REAL_ID})
    with Store(settings.runtime_dir).connect() as db:
        db.execute(
            "INSERT INTO browsing_history(user_id,paper_id,accessed_at) VALUES(1,?,'2000-01-01T00:00:00+00:00')",
            (REAL_ID,),
        )
    assert api.get("/api/me/browsing-history", headers=a).json()["total"] == 1
    assert api.get("/api/me/browsing-history", headers=b).json()["total"] == 0
    with TestClient(create_app(settings, es)) as reopened:
        assert reopened.get(route + "/papers", headers=a).json()["total"] == 1
        assert reopened.get("/api/me/browsing-history", headers=a).json()["total"] == 1
    record = api.get("/api/me/browsing-history", headers=a).json()["results"][0]
    assert api.delete("/api/me/browsing-history/" + str(record["id"]), headers=b).status_code == 404
    assert api.delete("/api/me/browsing-history/" + str(record["id"]), headers=a).status_code == 200
    api.delete("/api/me/favorites/" + REAL_ID, headers=a)
    assert api.get(route + "/papers", headers=a).json()["total"] == 0
    api.put(route + "/papers", headers=a, json={"paper_id": REAL_ID})
    assert api.delete(route, headers=a).status_code == 200
    assert api.get("/api/me/favorites/" + REAL_ID, headers=a).json()[
        "is_favorite"
    ]  # Folder deletion preserves global favorite.


def test_admin_user_disable_and_registration_cannot_escalate(v21):
    api, _, settings, _ = v21
    a = token(api)
    b = token(api, "ordinary_user")
    assert api.get("/api/admin/users", headers=b).status_code == 403
    with Store(settings.runtime_dir).connect() as db:
        db.execute("UPDATE users SET role='admin' WHERE id=1")
    assert api.patch("/api/admin/users/1", headers=a, json={"role": "user"}).status_code == 409
    assert api.patch("/api/admin/users/1", headers=a, json={"disabled": True}).status_code == 400
    assert api.patch("/api/admin/users/2", headers=a, json={"disabled": True}).status_code == 200
    assert api.get("/api/auth/me", headers=b).status_code == 401
    assert (
        api.post(
            "/api/auth/login",
            json={"username": "ordinary_user", "password": "V21-strong-password-123!"},
        ).status_code
        == 401
    )
    assert api.patch("/api/admin/users/2", headers=a, json={"disabled": False}).status_code == 200
    assert (
        api.post(
            "/api/auth/register",
            json={"username": "public_admin", "password": "Strong-password-123!", "role": "admin"},
        ).status_code
        == 400
    )
    assert "salt" not in api.get("/api/admin/users/2", headers=a).json()


def test_review_preview_notifications_and_admin_workflow(v21):
    api, _, settings, _ = v21
    a = token(api)
    b = token(api, "admin_user")
    with Store(settings.runtime_dir).connect() as db:
        db.execute("UPDATE users SET role='admin' WHERE id=2")
    item = api.post(
        "/api/uploads", headers=a, files={"file": ("review.pdf", pdf_bytes(), "application/pdf")}
    ).json()
    path = "/api/admin/uploads/" + item["id"] + "/pdf"
    assert api.get(path).status_code == 401 and api.get(path, headers=a).status_code == 403
    ranged = api.get(path, headers={**b, "Range": "bytes=0-4"})
    assert ranged.status_code == 206 and ranged.content == b"%PDF-"
    result = api.post(
        "/api/admin/uploads/" + item["id"] + "/review",
        headers=b,
        json={"decision": "reject", "reason": "needs revision"},
    )
    assert result.json()["status"] == "rejected"
    notices = api.get("/api/me/notifications", headers=a).json()
    assert (
        notices["total"] == 1 and api.get("/api/me/notifications", headers=b).json()["total"] == 0
    )
    nid = notices["results"][0]["id"]
    assert api.post(f"/api/me/notifications/{nid}/read", headers=b).status_code == 404
    assert api.post(f"/api/me/notifications/{nid}/read", headers=a).status_code == 200
    assert api.get("/api/me/papers", headers=a).json()["results"][0]["review_status"] == "rejected"
    own = api.post(
        "/api/admin/uploads",
        headers=b,
        files={"file": ("admin.pdf", pdf_bytes(), "application/pdf")},
    )
    assert own.status_code == 201 and own.json()["status"] == "approved"
    assert (
        api.post(
            "/api/admin/uploads",
            headers=a,
            files={"file": ("admin.pdf", pdf_bytes(), "application/pdf")},
        ).status_code
        == 403
    )


def test_real_docx_conversion_timeout_ocr_cleanup(v21, tmp_path):
    api, _, _, runtime = v21
    a = token(api)
    item = api.post(
        "/api/uploads",
        headers=a,
        files={"file": ("conversion.pdf", pdf_bytes(), "application/pdf")},
    ).json()
    response = api.get("/api/uploads/" + item["id"] + "/docx", headers=a)
    assert response.status_code == 200
    from docx import Document

    converted = Document(BytesIO(response.content))
    assert any("Controlled PDF conversion evidence" in p.text for p in converted.paragraphs)
    assert response.headers["X-ScholarLens-Conversion"] == "text-only"
    assert not list((runtime / "docx").glob("job-*"))
    with pytest.raises(Exception) as error:
        convert_pdf_to_docx(tmp_path / "missing.pdf", runtime / "docx", timeout=0.001)
    assert getattr(error.value, "status_code", None) == 504
    assert not list((runtime / "docx").glob("job-*"))
    assert api.get("/api/papers/" + REAL_ID + "/docx").status_code == 404


def test_migration_legacy_user_backup_restore_is_lossless(tmp_path):
    runtime = tmp_path / "legacy"
    runtime.mkdir()
    dbpath = runtime / "scholarlens.sqlite3"
    with sqlite3.connect(dbpath) as db:
        db.execute(
            "CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT UNIQUE,salt TEXT,password_hash TEXT,role TEXT,failures INTEGER DEFAULT 0,locked_until REAL DEFAULT 0,created_at TEXT)"
        )
        db.execute(
            "INSERT INTO users VALUES(42,'legacy','salt','original-hash','user',0,0,'2020-01-01')"
        )
    store = Store(str(runtime))
    with store.connect() as db:
        assert (
            db.execute("SELECT username,password_hash FROM users WHERE id=42").fetchone()[
                "password_hash"
            ]
            == "original-hash"
        )
        assert db.execute("SELECT version FROM schema_version").fetchone()[0] == 4
    backups = list((runtime / "db-backups").glob("*.sqlite3"))
    assert len(backups) == 1
    Store(str(runtime))
    assert len(list((runtime / "db-backups").glob("*.sqlite3"))) == 1
    restored = tmp_path / "restored.sqlite3"
    assert restore(restored, backups[0])["restored"]
    with sqlite3.connect(restored) as db:
        assert db.execute("SELECT username,password_hash FROM users").fetchone() == (
            "legacy",
            "original-hash",
        )
        assert "email_verified" not in {r[1] for r in db.execute("PRAGMA table_info(users)")}


def test_grounded_ai_context_summary_compare_stream_persist_isolate(v21, monkeypatch):
    api, es, settings, _ = v21
    a = token(api)
    b = token(api, "other_ai")
    calls = []

    def generated(s, q, e, **kwargs):
        calls.append({"question": q, "evidence": e, "history": kwargs.get("history", [])})
        from backend.rag import validate_answer

        answer = " ".join("Supported statement [" + ref["chunk_id"] + "]" for ref in e)
        return validate_answer(
            json.dumps(
                {
                    "answer": answer,
                    "citations": [
                        {"chunk_id": r["chunk_id"], "quote": r["quote"][:100]} for r in e
                    ],
                }
            ),
            e,
        )

    monkeypatch.setattr("backend.rag.generate", generated)
    configured = replace(
        settings,
        ai_api_key="controlled-test-key",
        ai_base_url="http://controlled.invalid/v1",
        ai_model="controlled-test-model",
    )
    with TestClient(create_app(configured, es)) as client:
        cid = client.post("/api/ai/conversations", headers=a, json={"title": "MRI"}).json()["id"]
        body = {
            "question": "magnetic resonance imaging",
            "paper_ids": [REAL_ID],
            "mode": "keyword",
            "conversation_id": cid,
        }
        first = client.post("/api/ask", headers=a, json=body)
        assert first.status_code == 200, first.text
        second = client.post(
            "/api/ask",
            headers=a,
            json={**body, "question": "How does that method work?", "stream": True},
        )
        assert second.status_code == 200 and second.headers["content-type"].startswith(
            "text/event-stream"
        )
        assert "event: done" in second.text and calls[-1]["history"][0]["role"] == "user"
        assert len(client.get("/api/ai/conversations/" + cid + "/messages", headers=a).json()) == 4
        assert (
            client.get("/api/ai/conversations/" + cid + "/messages", headers=b).status_code == 404
        )
        assert client.post("/api/ask", headers=b, json=body).status_code == 404
        summary = client.post(
            "/api/ai/summarize",
            json={"question": "Focus on methods", "paper_ids": [REAL_ID], "top_k": 4},
        )
        assert summary.status_code == 200 and summary.json()["operation"] == "summarize", (
            summary.text
        )
        compare = client.post(
            "/api/ai/compare",
            json={"question": "Compare methods", "paper_ids": [REAL_ID, OTHER_ID], "top_k": 6},
        )
        assert compare.status_code == 200, compare.text
        assert {r["paper_id"] for r in compare.json()["citations"]} == {REAL_ID, OTHER_ID}
        assert "Compare each" in calls[-1]["question"]
    with TestClient(create_app(settings, es)) as restored:
        assert (
            len(restored.get("/api/ai/conversations/" + cid + "/messages", headers=a).json()) == 4
        )


def test_streaming_rejects_invalid_citations_before_content(v21, monkeypatch):
    _, es, settings, _ = v21
    from backend.accounts import problem

    def invalid(*args, **kwargs):
        raise problem(502, "ai_invalid_citations", "controlled citation failure")

    monkeypatch.setattr("backend.rag.generate", invalid)
    with TestClient(
        create_app(
            replace(
                settings,
                ai_api_key="test-only",
                ai_base_url="http://controlled.invalid",
                ai_model="fixture",
            ),
            es,
        )
    ) as api:
        response = api.post(
            "/api/ask",
            json={
                "question": "magnetic resonance",
                "paper_ids": [REAL_ID],
                "mode": "keyword",
                "stream": True,
            },
        )
        assert response.status_code == 502 and response.headers["content-type"].startswith(
            "application/json"
        )
        assert "event: answer" not in response.text
