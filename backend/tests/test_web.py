"""Production SPA routes cannot replace API errors or serve files outside dist."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.web import mount_frontend


def test_same_origin_static_and_spa_boundaries(tmp_path):
    dist=tmp_path/"dist";dist.mkdir();(dist/"assets").mkdir()
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
