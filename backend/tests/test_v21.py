"""V2.1 parity tests use a temporary SQLite runtime and isolated upload records."""

from dataclasses import replace
from io import BytesIO
import uuid
import json
from elasticsearch import Elasticsearch
from fastapi.testclient import TestClient
from pypdf import PdfWriter
import pytest
from backend.app1 import create_app
from backend.config import Settings
from backend.porter_compare import compare
from backend.import_jsonl import import_records
from backend.upload_vector import vectorize_uploads

REAL_ID = "source-sha256:00a0e8b16d0dda799ea25a2f38579c3c203ac076f04d2949c86247f65e98baae"


@pytest.fixture
def v21(tmp_path):
    settings = replace(
        Settings(),
        runtime_dir=str(tmp_path),
        uploads_index="scholarlens-uploads-v21-" + uuid.uuid4().hex[:8] + "-real",
        upload_vector_index="scholarlens-vectors-uploads-v21-" + uuid.uuid4().hex[:8],
    )
    es = Elasticsearch(settings.url)
    assert es.count(index=settings.index)["count"] == 859
    with TestClient(create_app(settings, es)) as api:
        yield api, es, settings, tmp_path
    es.close()


def token(api, username="v21_user"):
    body = {"username": username, "password": "V21-strong-password-123!"}
    assert api.post("/api/auth/register", json=body).status_code == 201
    result = api.post("/api/auth/login", json=body)
    assert result.status_code == 200
    return {"Authorization": "Bearer " + result.json()["access_token"]}


def pdf_bytes():
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

    page = writer.pages[0]
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 30 250 Td (Controlled PDF conversion evidence) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    writer.write(output)
    return output.getvalue()


def test_profile_password_reset_and_notifications(v21):
    api, _, _, _ = v21
    headers = token(api)
    profile = api.get("/api/me/profile", headers=headers)
    assert profile.status_code == 200 and profile.json()["display_name"] == ""
    updated = api.patch(
        "/api/me/profile",
        headers=headers,
        json={"display_name": "V2.1 User", "email": "user@example.com"},
    )
    assert updated.status_code == 200 and updated.json()["display_name"] == "V2.1 User"
    assert (
        api.post("/api/auth/password-reset/request", json={"email": "user@example.com"}).status_code
        == 503
    )
    changed = api.post(
        "/api/auth/password",
        headers=headers,
        json={
            "current_password": "V21-strong-password-123!",
            "new_password": "V21-new-password-456!",
        },
    )
    assert changed.status_code == 200
    assert api.get("/api/auth/me", headers=headers).status_code == 401
    assert (
        api.post(
            "/api/auth/login", json={"username": "v21_user", "password": "V21-strong-password-123!"}
        ).status_code
        == 401
    )


def test_folders_browsing_history_and_random_batches(v21):
    api, _, _, _ = v21
    headers = token(api)
    folder = api.post("/api/me/favorite-folders", headers=headers, json={"name": "Methods"})
    assert folder.status_code == 201
    folder_id = folder.json()["id"]
    assert (
        api.put(
            f"/api/me/favorite-folders/{folder_id}/papers",
            headers=headers,
            json={"paper_id": REAL_ID},
        ).status_code
        == 200
    )
    assert (
        api.get(f"/api/me/favorite-folders/{folder_id}/papers", headers=headers).json()["total"]
        == 1
    )
    assert (
        api.patch(
            f"/api/me/favorite-folders/{folder_id}", headers=headers, json={"name": "Renamed"}
        ).json()["name"]
        == "Renamed"
    )
    assert (
        api.post(
            "/api/me/browsing-history", headers=headers, json={"paper_id": REAL_ID}
        ).status_code
        == 201
    )
    history = api.get("/api/me/browsing-history?days=7", headers=headers).json()
    assert history["total"] == 1 and history["results"][0]["paper_id"] == REAL_ID
    assert api.delete("/api/me/browsing-history", headers=headers).json()["cleared"]
    first = api.get("/api/discover/random?limit=3&seed=one").json()
    second = api.get(
        "/api/discover/random?limit=3&seed=two&exclude="
        + ",".join(x["paper_id"] for x in first["recommendations"])
    ).json()
    assert len(first["recommendations"]) == 3 and len(second["recommendations"]) == 3
    assert not {x["paper_id"] for x in first["recommendations"]} & {
        x["paper_id"] for x in second["recommendations"]
    }


def settings_store(settings):
    from backend.accounts import Store

    return Store(settings.runtime_dir).connect()


def test_admin_users_upload_preview_docx_and_notifications(v21):
    api, _, settings, _ = v21
    headers = token(api, "v21_admin")
    with settings_store(settings) as db:
        db.execute("UPDATE users SET role='admin' WHERE username='v21_admin'")
    upload = api.post(
        "/api/uploads",
        headers=headers,
        files={"file": ("review.pdf", pdf_bytes(), "application/pdf")},
    )
    assert upload.status_code == 201
    upload_id = upload.json()["id"]
    assert api.get(f"/api/admin/uploads/{upload_id}/pdf", headers=headers).status_code == 200
    docx = api.get(f"/api/uploads/{upload_id}/docx", headers=headers)
    assert (
        docx.status_code == 200
        and docx.headers["content-type"].startswith("application/vnd.openxmlformats")
        and docx.content[:2] == b"PK"
    )
    from docx import Document

    assert "Controlled PDF conversion evidence" in "\n".join(
        p.text for p in Document(BytesIO(docx.content)).paragraphs
    )
    users = api.get("/api/admin/users", headers=headers)
    assert users.status_code == 200 and users.json()["total"] >= 1
    detail = api.get("/api/admin/users/1", headers=headers)
    assert detail.status_code == 200 and "password_hash" not in detail.text
    assert (
        api.post(
            f"/api/admin/uploads/{upload_id}/review",
            headers=headers,
            json={"decision": "approve", "reason": "test"},
        ).status_code
        == 200
    )
    notices = api.get("/api/me/notifications", headers=headers)
    assert notices.status_code == 200 and notices.json()["total"] >= 1
    assert api.get("/api/me/uploads", headers=headers).status_code == 200


def test_ai_sessions_summary_compare_and_external_status(v21):
    api, _, _, _ = v21
    headers = token(api, "v21_ai")
    conversation = api.post(
        "/api/ai/conversations", headers=headers, json={"title": "MRI questions"}
    )
    assert conversation.status_code == 201
    cid = conversation.json()["id"]
    assert api.get("/api/ai/conversations", headers=headers).json()[0]["id"] == cid
    assert (
        api.post(
            "/api/ask", headers=headers, json={"question": "What is MRI?", "conversation_id": cid}
        ).json()["error"]["code"]
        == "ai_not_configured"
    )
    assert (
        api.post("/api/ai/summarize", json={"question": "x", "paper_ids": [REAL_ID]}).status_code
        == 503
    )
    assert (
        api.post("/api/ai/compare", json={"question": "x", "paper_ids": [REAL_ID]}).status_code
        == 400
    )
    assert api.get(f"/api/ai/conversations/{cid}/messages", headers=headers).status_code == 200
    assert api.delete(f"/api/ai/conversations/{cid}", headers=headers).json()["deleted"]


def test_porter_comparison_is_ephemeral():
    result = compare()
    assert result["formal_indices_modified"] is False
    assert "retriev" in result["porter_tokens"]
    assert result["retrieve_query_hits"] == 1


def test_upload_vectorization_is_independent(v21, tmp_path):
    api, es, settings, _ = v21
    doc = {
        "paper_id": "upload-sha256:" + "a" * 64,
        "title": "Controlled semantic upload",
        "authors": ["Test Author"],
        "date": "2024-01-01",
        "year": 2024,
        "affiliation": [],
        "address": [],
        "pages": {"first": None, "last": None, "count": 1},
        "abstract": "brain magnetic resonance imaging",
        "fulltext": "brain magnetic resonance imaging methods and results",
        "pdf_path": "",
        "source_file": "controlled.pdf",
        "parse_status": "success",
        "errors": [],
    }
    source = tmp_path / "upload.jsonl"
    source.write_text(json.dumps(doc) + "\n", encoding="utf-8")
    records, meta = __import__("backend.import_jsonl", fromlist=["load_jsonl"]).load_jsonl(
        source, "real"
    )
    import_records(es, settings.uploads_index, records, meta)
    result = vectorize_uploads(settings)
    assert result["status"] == "ready" and result["chunks"] > 0
    assert es.count(index=settings.index)["count"] == 859
    assert es.count(index=settings.upload_vector_index)["count"] == result["chunks"]
    actual_chunk = es.search(index=settings.upload_vector_index, size=1)["hits"]["hits"][0][
        "_source"
    ]
    assert api.get("/api/chunks/" + actual_chunk["chunk_id"]).json()["text"] == actual_chunk["text"]
    previous = result["generation"]
    rebuilt = vectorize_uploads(settings)
    assert rebuilt["reused_chunks"] == result["chunks"] and rebuilt["embedded_chunks"] == 0
    assert es.indices.exists(index=previous) and previous in rebuilt["previous_generations"]
    for mode in ("keyword", "semantic", "hybrid"):
        response = api.get(
            "/api/search",
            params={
                "q": "Controlled semantic upload",
                "mode": mode,
                "field": "title",
                "page_size": 100,
            },
        )
        assert response.status_code == 200, response.text
        assert doc["paper_id"] in {r["paper_id"] for r in response.json()["results"]}
        selected = next(r for r in response.json()["results"] if r["paper_id"] == doc["paper_id"])
        assert selected["authors"] == ["Test Author"] and selected["year"] == 2024
