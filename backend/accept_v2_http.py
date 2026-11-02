"""Actual isolated Windows API restart acceptance; never return credentials or tokens."""

import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import uuid

import httpx

PAPER = "source-sha256:00a0e8b16d0dda799ea25a2f38579c3c203ac076f04d2949c86247f65e98baae"


def accept(port: int, output: Path):
    root = Path.cwd()
    runtime = root / "backend/.runtime" / ("v2-http-" + uuid.uuid4().hex[:10])
    runtime.mkdir(parents=True)
    env = os.environ.copy()
    env["SCHOLARLENS_RUNTIME_DIR"] = str(runtime)
    env["ELASTICSEARCH_INDEX"] = "scholarlens-papers-real"
    for key in ("AI_API_KEY", "AI_MODEL", "AI_BASE_URL", "GROBID_URL"):
        env.pop(key, None)
    startup = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        "infra/start-backend1.ps1",
        "-Port",
        str(port),
    ]
    stop = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        "infra/stop-backend.ps1",
        "-Port",
        str(port),
    ]

    def command(args):
        with (runtime / "process.log").open("ab") as f:
            result = subprocess.run(args, env=env, stdout=f, stderr=subprocess.STDOUT, timeout=90)
        if result.returncode:
            raise RuntimeError("owned API lifecycle command failed; inspect isolated process.log")

    report = {"test_only": True, "port": port, "checks": {}}
    with httpx.Client(timeout=3, trust_env=False) as probe:
        try:
            probe.get(f"http://127.0.0.1:{port}/openapi.json")
        except httpx.ConnectError:
            pass
        else:
            raise RuntimeError("acceptance port already has a service; it was preserved")
    command(startup)
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=60, trust_env=False) as api:
            stats = api.get("/api/stats")
            assert (
                stats.status_code == 200
                and stats.json()["indexed"] == 859
                and stats.json()["status"] == "real"
            )
            report["checks"]["real_base_859"] = True
            password = secrets.token_urlsafe(24)
            account = {"username": "v2_acceptance_user", "password": password}
            assert api.post("/api/auth/register", json=account).status_code == 201
            result = api.post("/api/auth/login", json=account)
            assert result.status_code == 200
            headers = {"Authorization": "Bearer " + result.json()["access_token"]}
            assert api.put("/api/me/favorites/" + PAPER, headers=headers).status_code == 200
            assert (
                api.post(
                    "/api/me/history", json={"q": "magnetic", "field": "title"}, headers=headers
                ).status_code
                == 201
            )
            report["checks"]["actual_http_personal_writes"] = True
            command(stop)
            command(startup)
            assert api.get("/api/auth/me", headers=headers).status_code == 200
            assert (
                api.get("/api/me/favorites", headers=headers).json()["results"][0]["paper_id"]
                == PAPER
            )
            assert (
                api.get("/api/me/history", headers=headers).json()["results"][0]["q"] == "magnetic"
            )
            report["checks"]["sqlite_sessions_favorites_history_survive_process_restart"] = True
            found = api.get("/api/search?q=magnetic&field=title").json()
            assert found["total"] == 1 and found["results"][0]["paper_id"] == PAPER
            report["checks"]["keyword_search_after_restart"] = True
            assert api.post("/api/auth/logout", headers=headers).json()["logged_out"]
            assert api.get("/api/auth/me", headers=headers).status_code == 401
            report["checks"]["revoked_session_401"] = True
            assert (
                api.post("/api/ask", json={"question": "What is MRI?"}).json()["error"]["code"]
                == "ai_not_configured"
            )
            report["checks"]["ai_not_configured"] = True
            schema = api.get("/openapi.json").json()
            report["application_version"] = schema["info"]["version"]
            report["routes"] = sorted(schema["paths"])
            report["stats"] = api.get("/api/stats").json()
            report["capabilities"] = api.get("/api/capabilities").json()
    finally:
        command(stop)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "checks": report["checks"],
        "application_version": report["application_version"],
        "output": str(output),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8004)
    parser.add_argument(
        "--output", type=Path, default=Path("backend/.runtime/v2-http-restart.json")
    )
    args = parser.parse_args()
    print(json.dumps(accept(args.port, args.output), indent=2))
