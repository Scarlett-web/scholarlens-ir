"""Actual isolated HTTP-process acceptance for V2.1, without writing personal test data to the main database."""

import argparse
from io import BytesIO
import json
import os
from pathlib import Path
import secrets
import subprocess
import uuid
import httpx
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

PAPER = "source-sha256:00a0e8b16d0dda799ea25a2f38579c3c203ac076f04d2949c86247f65e98baae"


def controlled_pdf():
    output = BytesIO()
    w = PdfWriter()
    page = w.add_blank_page(width=300, height=300)
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
    page[NameObject("/Contents")] = w._add_object(stream)
    w.write(output)
    return output.getvalue()


def accept(port=8004):
    root = Path.cwd()
    runtime = root / "backend/.runtime" / ("v21-http-" + uuid.uuid4().hex[:8])
    runtime.mkdir()
    env = os.environ.copy()
    env["SCHOLARLENS_RUNTIME_DIR"] = str(runtime)
    for key in (
        "AI_API_KEY",
        "AI_MODEL",
        "AI_BASE_URL",
        "GROBID_URL",
        "EMAIL_BASE_URL",
        "EMAIL_API_KEY",
    ):
        env.pop(key, None)

    def cmd(args):
        with (runtime / "lifecycle.log").open("ab") as log:
            r = subprocess.run(args, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=90)
        if r.returncode:
            raise RuntimeError("owned API lifecycle failed, inspect private log")

    common = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"]
    start = common + ["infra/start-backend1.ps1", "-Port", str(port)]
    stop = common + ["infra/stop-backend.ps1", "-Port", str(port)]
    with httpx.Client(trust_env=False, timeout=3) as c:
        try:
            c.get(f"http://127.0.0.1:{port}/openapi.json")
        except httpx.ConnectError:
            pass
        else:
            raise RuntimeError("port occupied; service preserved")
    report = {"test_only": True, "port": port, "checks": {}}
    cmd(start)
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=60) as api:
            password = secrets.token_urlsafe(24)
            credentials = {"username": "v21_http_acceptance", "password": password}
            assert api.post("/api/auth/register", json=credentials).status_code == 201
            login = api.post("/api/auth/login", json=credentials)
            headers = {"Authorization": "Bearer " + login.json()["access_token"]}
            assert (
                api.patch(
                    "/api/me/profile",
                    headers=headers,
                    json={"display_name": "Acceptance", "email": "fixture@example.invalid"},
                ).status_code
                == 200
            )
            folder = api.post(
                "/api/me/favorite-folders", headers=headers, json={"name": "Evidence"}
            ).json()
            route = "/api/me/favorite-folders/" + str(folder["id"]) + "/papers"
            assert api.put(route, headers=headers, json={"paper_id": PAPER}).status_code == 200
            assert (
                api.post(
                    "/api/me/browsing-history", headers=headers, json={"paper_id": PAPER}
                ).status_code
                == 201
            )
            conv = api.post(
                "/api/ai/conversations", headers=headers, json={"title": "Persistent context"}
            ).json()["id"]
            cmd(stop)
            cmd(start)
            assert (
                api.get("/api/me/profile", headers=headers).json()["display_name"] == "Acceptance"
            )
            assert api.get(route, headers=headers).json()["total"] == 1
            assert api.get("/api/me/browsing-history", headers=headers).json()["total"] == 1
            assert api.get("/api/ai/conversations", headers=headers).json()[0]["id"] == conv
            report["checks"][
                "profile_folders_browsing_conversation_and_session_survive_process_restart"
            ] = True
            item = api.post(
                "/api/uploads",
                headers=headers,
                files={"file": ("controlled.pdf", controlled_pdf(), "application/pdf")},
            )
            assert item.status_code == 201, item.text
            upload_id = item.json()["id"]
            converted = api.get("/api/uploads/" + upload_id + "/docx", headers=headers)
            assert converted.status_code == 200
            output = root / "backend/.runtime/v21-http-converted.docx"
            output.write_bytes(converted.content)
            from docx import Document

            assert any(
                "Controlled PDF conversion evidence" in p.text for p in Document(output).paragraphs
            )
            report["checks"]["actual_http_docx_generated_reopened"] = True
            report["conversion_artifact"] = str(output)
            assert not list((runtime / "docx").glob("job-*"))
            report["checks"]["conversion_temporary_files_cleaned"] = True
            preview = "/api/admin/uploads/" + upload_id + "/pdf"
            assert api.get(preview, headers=headers).status_code == 403
            cmd(
                [
                    str(root / "backend/.venv/Scripts/python.exe"),
                    "-m",
                    "backend.accounts",
                    "--promote",
                    "v21_http_acceptance",
                ]
            )
            ranged = api.get(preview, headers={**headers, "Range": "bytes=0-4"})
            assert ranged.status_code == 206 and ranged.content == b"%PDF-"
            assert api.get(preview).status_code == 401
            assert (
                api.post(
                    "/api/admin/uploads/" + upload_id + "/review",
                    headers=headers,
                    json={"decision": "approve", "reason": "controlled fixture"},
                ).status_code
                == 200
            )
            assert api.get("/api/me/notifications", headers=headers).json()["total"] == 1
            failed = api.post("/api/admin/uploads/" + upload_id + "/process", headers=headers)
            assert failed.status_code == 503
            report["checks"]["admin_preview_review_notification_and_missing_grobid_honest"] = True
            assert (
                api.post(
                    "/api/auth/password-reset/request", json={"email": "fixture@example.invalid"}
                ).json()["error"]["code"]
                == "email_not_configured"
            )
            assert (
                api.post("/api/ai/summarize", json={"paper_ids": [PAPER]}).json()["error"]["code"]
                == "ai_not_configured"
            )
            report["checks"]["external_ai_email_unconfigured"] = True
            before = api.get("/api/discover/random?limit=3").json()["recommendations"]
            after = api.get(
                "/api/discover/random",
                params={"limit": 3, "exclude": ",".join(d["paper_id"] for d in before)},
            ).json()["recommendations"]
            assert not {d["paper_id"] for d in before} & {d["paper_id"] for d in after}
            report["checks"]["actual_random_change_batch"] = True
            report["stats"] = api.get("/api/stats").json()
            assert report["stats"]["indexed"] == 859
            report["version"] = api.get("/openapi.json").json()["info"]["version"]
    finally:
        cmd(stop)
    (root / "backend/.runtime/v21-http-verification.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8004)
    result = accept(parser.parse_args().port)
    print(
        json.dumps(
            {
                "checks": result["checks"],
                "version": result["version"],
                "indexed": result["stats"]["indexed"],
            },
            indent=2,
        )
    )
