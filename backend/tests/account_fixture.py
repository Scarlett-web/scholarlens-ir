"""Isolated real account/workspace routes; no ES, email, supplier or production settings."""
import argparse
import json
from pathlib import Path
import secrets
import socket

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.accounts import Store, router as account_router
from backend.workspace import router as workspace_router
from backend.web import mount_frontend


PAPER = {
    "paper_id": "fixture:account-paper", "title": "Isolated account fixture paper",
    "authors": [], "abstract": "Explicit synthetic account acceptance fixture.",
    "fulltext": "Fixture text; never part of the research index.", "year": None,
    "keywords": [], "affiliation": [], "address": [], "topics": [], "date": "",
    "pages": None, "parse_status": "partial", "pdf_available": False,
}


def create_fixture_app(runtime: Path, frontend=None, challenge=""):
    store = Store(str(runtime))
    app = FastAPI()

    def read_paper(paper_id):
        if paper_id != PAPER["paper_id"]:
            raise HTTPException(404)
        return dict(PAPER), "isolated-fixture"

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        # Same public error envelope as backend.app; never import its default app/settings.
        detail = exc.detail if isinstance(exc.detail, dict) else {
            "code": "not_found", "message": str(exc.detail), "details": {},
        }
        return JSONResponse(status_code=exc.status_code, content={"error": detail}, headers=exc.headers)

    @app.get("/__isolated_account_fixture__")
    def identity(value: str = ""):
        if not challenge or not secrets.compare_digest(value, challenge):
            raise HTTPException(404)
        return {"isolated": True, "challenge": challenge, "external_services": False}

    @app.get("/api/stats")
    def stats():
        return {"papers": 1, "indexed": 1, "status": "mock"}

    @app.get("/api/capabilities")
    def capabilities():
        return {"modules": {"authentication": {"status": "ready"}}}

    app.include_router(account_router(store, read_paper))
    app.include_router(workspace_router(store, read_paper))
    mount_frontend(app, frontend)
    return app, store


def main():
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    reports = (repo / "tools/audit/reports").resolve(strict=True)
    output = Path(arguments.output).resolve(strict=True)
    assert output.is_relative_to(reports) and output != reports
    runtime = output / "isolated-runtime"
    runtime.mkdir(exist_ok=False)
    challenge = secrets.token_urlsafe(24)
    app, _ = create_fixture_app(runtime, repo / "frontend/dist", challenge)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        listener.setblocking(False)
        print(json.dumps({"port": listener.getsockname()[1], "challenge": challenge}), flush=True)
        server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
        server.run(sockets=[listener])


if __name__ == "__main__":
    main()
