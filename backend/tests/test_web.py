"""Production SPA routes cannot replace API errors or serve files outside dist."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.web import mount_frontend


def test_same_origin_static_and_spa_boundaries(tmp_path):
    dist=tmp_path/"dist"
    dist.mkdir()
    (dist/"assets").mkdir()
    (dist/"index.html").write_text("<html>ScholarLens frontend</html>")
    (dist/"assets/app.js").write_text("console.log('test')")
    (dist/".env").write_text("PRIVATE_TEST_VALUE")
    (tmp_path/"outside.txt").write_text("private")
    app=FastAPI()
    @app.get("/api/check")
    def check():return {"ok":True}
    mount_frontend(app,str(dist))
    with TestClient(app) as client:
        for path in ("/", "/search", "/paper/source-sha256:test", "/account"):
            response=client.get(path)
            assert response.status_code==200 and "ScholarLens frontend" in response.text
        assert client.get("/assets/app.js").status_code==200
        assert client.get("/api/check").json()=={"ok":True}
        for path in ("/api/missing", "/assets/missing.js", "/.env", "/%2e%2e/outside.txt"):
            result=client.get(path)
            assert result.status_code==404 and "PRIVATE_TEST_VALUE" not in result.text


def test_browser_headers_preserve_pdf_ranges_and_private_responses(tmp_path):
    from fastapi.responses import FileResponse

    (tmp_path / "index.html").write_text("<html>ScholarLens</html>")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "index-abcdefgh.js").write_text("console.log('static')")
    (assets / "plain.js").write_text("console.log('plain')")
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4\ncontrolled PDF response")
    app = FastAPI()

    @app.get("/api/papers/test/pdf")
    def paper():
        return FileResponse(pdf, media_type="application/pdf")

    @app.get("/api/me/profile")
    def profile():
        return {"username": "controlled"}

    @app.get("/api/uploads")
    def uploads():
        return {"items": []}

    @app.post("/api/ask")
    def ask():
        return {"answer": "controlled"}

    mount_frontend(app, str(tmp_path))
    with TestClient(app) as client:
        for route in ["/", "/assistant", "/api/me/profile", "/assets/index-abcdefgh.js", "/api/missing"]:
            response = client.get(route)
            assert response.headers["x-content-type-options"] == "nosniff"
            assert response.headers["x-frame-options"] == "SAMEORIGIN"
            assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
        assert client.get("/api/me/profile").headers["cache-control"] == "no-store"
        assert client.get("/api/uploads").headers["cache-control"] == "no-store"
        assert client.post("/api/ask").headers["cache-control"] == "no-store"
        assert client.get("/api/papers/test/pdf", headers={"Authorization": "Bearer controlled"}).headers["cache-control"] == "no-store"
        assert client.get("/").headers["cache-control"] == "no-cache"
        assert client.get("/assistant").headers["cache-control"] == "no-cache"
        assert client.get("/assets/index-abcdefgh.js").headers["cache-control"] == "public, max-age=31536000, immutable"
        assert client.get("/assets/plain.js").headers["cache-control"] == "public, max-age=3600"
        response = client.get("/api/papers/test/pdf", headers={"Range": "bytes=0-4"})
        assert response.status_code == 206 and response.content == b"%PDF-"
        assert response.headers["content-type"] == "application/pdf"
        assert "content-range" in response.headers


def test_api_only_private_responses_keep_browser_boundaries(tmp_path):
    from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

    pdf = tmp_path / "private.pdf"
    pdf.write_bytes(b"%PDF-1.4\nexplicit synthetic fixture")
    app = FastAPI()

    @app.get("/api/admin/uploads/fixture/pdf")
    def private_pdf():
        return FileResponse(pdf, media_type="application/pdf")

    @app.get("/api/me/workspace")
    def private_workspace():
        return JSONResponse({"fixture": True}, headers={"Cache-Control": "public, max-age=3600"})

    @app.get("/api/ai/fixture-stream")
    def private_stream():
        return StreamingResponse(iter(["event: done\ndata: fixture\n\n"]), media_type="text/event-stream")

    mount_frontend(app, None)
    with TestClient(app) as client:
        for path in ("/api/me/workspace", "/api/admin/uploads/fixture/pdf", "/api/ai/fixture-stream"):
            response = client.get(path)
            assert response.status_code == 200
            assert response.headers.get("cache-control") == "no-store"
            assert response.headers.get("x-content-type-options") == "nosniff"
        ranged = client.get("/api/admin/uploads/fixture/pdf", headers={"Range": "bytes=0-4"})
        assert ranged.status_code == 206 and ranged.content == b"%PDF-"
        assert ranged.headers["cache-control"] == "no-store"
        assert client.get("/").status_code == 404
