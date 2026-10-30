"""Run fixed GET-only ZAP jobs against an owned synthetic account fixture, never a URL."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.request

REPO = Path(__file__).resolve().parents[2]
REPORTS = REPO / "tools/audit/reports"
ARCHIVE_HASH = "94c8f767b1c2e94f0db66b3ae56514d5e3f5a728ee1b6c798e0c8fe2d61fbff0"
ROUTES = {"/": 200, "/account": 200, "/library": 200, "/robots.txt": 200,
          "/api/stats": 200, "/api/capabilities": 200,
          "/api/auth/me": 401, "/api/me/workspace": 401}


def validate_plan(plan: dict, origin: str) -> None:
    assert re.fullmatch(r"http://127\.0\.0\.1:[1-9][0-9]{0,4}", origin)
    assert plan["env"]["contexts"][0]["urls"] == [origin]
    assert [job["type"] for job in plan["jobs"]] == ["requestor", "passiveScan-wait", "report"]
    requests = plan["jobs"][0]["requests"]
    assert len(requests) == len(ROUTES)
    for item, (path, status) in zip(requests, ROUTES.items()):
        assert item == {"url": origin + path, "method": "GET", "responseCode": status}


def plan_for(origin: str, output: Path) -> dict:
    plan = {"env": {"contexts": [{"name": "owned-synthetic-read-only", "urls": [origin],
                                   "includePaths": [re.escape(origin) + r"/.*"]}],
                    "parameters": {"failOnError": True, "failOnWarning": True}},
            "jobs": [
                {"type": "requestor", "requests": [
                    {"url": origin + path, "method": "GET", "responseCode": status}
                    for path, status in ROUTES.items()]},
                {"type": "passiveScan-wait", "parameters": {"maxDuration": 1}},
                {"type": "report", "parameters": {"template": "traditional-json",
                    "reportDir": str(output), "reportFile": "zap-passive",
                    "reportTitle": "ScholarLens isolated passive GET checks", "displayReport": False}}]}
    validate_plan(plan, origin)
    return plan


def serve_fixture(output: Path) -> None:
    # Import the isolated factory, never backend.app or its production settings.
    sys.path.insert(0, str(REPO))
    import uvicorn
    from fastapi.responses import JSONResponse
    from backend.tests.account_fixture import create_fixture_app

    assert output.resolve().is_relative_to(REPORTS.resolve())
    runtime = output / "fixture-runtime"
    runtime.mkdir(exist_ok=False)
    challenge = secrets.token_urlsafe(24)
    app, _ = create_fixture_app(runtime, REPO / "frontend/dist", challenge)

    @app.middleware("http")
    async def fixed_read_guard(request, call_next):
        allowed = request.url.path in ROUTES or request.url.path == "/__isolated_account_fixture__"
        response = await call_next(request) if request.method == "GET" and allowed else JSONResponse(status_code=405, content={"error": "fixture_read_guard"})
        with (output / "fixture-requests.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"method": request.method, "path": request.url.path,
                                     "status": response.status_code}) + "\n")
        return response

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        listener.setblocking(False)
        print(json.dumps({"port": listener.getsockname()[1], "challenge": challenge}), flush=True)
        uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False)).run(sockets=[listener])


def run() -> int:
    output = REPORTS / ("zap-passive-" + time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(4))
    output.mkdir(parents=True, exist_ok=False)
    report = {"passed": False, "scope": "8 fixed GETs, synthetic isolated account/workspace factory; no authenticated flows, ES, production or active scan", "output": str(output)}
    server = None
    try:
        java = shutil.which("java")
        assert java, "Java is unavailable"
        install = REPO / "tools/audit/bin/zap-2.17.0/ZAP_2.17.0"
        archive = REPO / "tools/audit/.downloads/ZAP_2.17.0_Crossplatform.zip"
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == ARCHIVE_HASH
        assert (install / "zap-2.17.0.jar").is_file()
        build = json.loads((REPO / "frontend/dist/build-info.json").read_text(encoding="utf-8"))
        assert build["data_source"] == "api", "Build the real API production frontend first"
        home = output / "zap-home"
        home.mkdir()
        env = {key: value for key, value in os.environ.items() if not key.startswith(("AI_", "SMTP_", "SCHOLARLENS_", "ELASTICSEARCH_", "GROBID_", "ZAP_AUTH_"))}
        env.update(PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1", PYTHONUNBUFFERED="1")
        with (output / "fixture.log").open("w", encoding="utf-8") as error_log:
            server = subprocess.Popen([sys.executable, "-u", str(Path(__file__).resolve()), "--serve-fixture", str(output)], cwd=REPO, env=env, stdout=subprocess.PIPE, stderr=error_log, text=True, encoding="utf-8")
            messages: queue.Queue = queue.Queue()
            threading.Thread(target=lambda: messages.put(server.stdout.readline()), daemon=True).start()
            identity = json.loads(messages.get(timeout=20))
            assert 0 < identity["port"] < 65536
            origin = "http://127.0.0.1:" + str(identity["port"])
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for attempt in range(50):
                try:
                    with opener.open(origin + "/__isolated_account_fixture__?value=" + identity["challenge"], timeout=1) as response:
                        assert json.load(response) == {"isolated": True, "challenge": identity["challenge"], "external_services": False}
                    break
                except OSError:
                    if server.poll() is not None:
                        raise RuntimeError("Owned fixture exited")
                    time.sleep(.1)
            else:
                raise RuntimeError("Owned fixture did not become ready")
            plan = plan_for(origin, output)
            (output / "plan.yaml").write_text(json.dumps(plan, indent=2), encoding="utf-8")
            with socket.socket() as reserve:
                reserve.bind(("127.0.0.1", 0))
                proxy_port = reserve.getsockname()[1]
            command = [java, "-Xmx512m", "-Djava.awt.headless=true", "-jar", str(install / "zap-2.17.0.jar"),
                       "-cmd", "-silent", "-notel", "-dir", str(home), "-installdir", str(install),
                       "-host", "127.0.0.1", "-port", str(proxy_port), "-config", "mode=safe", "-autorun", str(output / "plan.yaml")]
            with (output / "zap.log").open("w", encoding="utf-8") as log:
                result = subprocess.run(command, cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=180)
            report["zap_exit_code"] = result.returncode
            assert result.returncode == 0, "ZAP plan failed; inspect retained zap.log"
            raw = json.loads((output / "zap-passive.json").read_text(encoding="utf-8-sig"))
            rows = [json.loads(line) for line in (output / "fixture-requests.jsonl").read_text(encoding="utf-8").splitlines()]
            assert all(row["method"] == "GET" for row in rows)
            observed = [row for row in rows if row["path"] != "/__isolated_account_fixture__"]
            assert len(observed) == len(ROUTES)
            assert {row["path"]: row["status"] for row in observed} == ROUTES
            for site in raw.get("site", []):
                assert site["@name"] == origin
            db = output / "fixture-runtime/scholarlens.sqlite3"
            with sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True) as connection:
                assert connection.execute("SELECT count(*) FROM users").fetchone()[0] == 0
            report.update(passed=True, origin=origin, requests=observed, users=0,
                          alerts=[{"name": alert.get("name"), "risk": alert.get("riskdesc"), "instances": len(alert.get("instances", []))}
                                  for site in raw.get("site", []) for alert in site.get("alerts", [])],
                          tool={"version": "2.17.0", "archive_sha256": ARCHIVE_HASH, "unsolicited_requests": "disabled by -silent/-notel", "home": str(home)})
    except Exception as error:
        report["error"] = str(error)
    finally:
        if server and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=10)
        report["fixture_stopped"] = server is None or server.poll() is not None
        report["passed"] = report["passed"] and report["fixture_stopped"]
        (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--serve-fixture", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.serve_fixture:
        serve_fixture(args.serve_fixture)
    elif args.self_test:
        plan = plan_for("http://127.0.0.1:12345", Path("isolated-output"))
        plan["jobs"].insert(0, {"type": "activeScan"})
        try:
            validate_plan(plan, "http://127.0.0.1:12345")
        except AssertionError:
            print("PASS fixed GET plan rejects active scan jobs")
        else:
            raise AssertionError("An active job was accepted")
    else:
        raise SystemExit(run())
