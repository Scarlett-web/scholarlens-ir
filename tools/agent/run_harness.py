"""Execute checked-in agent cases locally and preserve real exit codes and JUnit."""
import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, help="Backend interpreter (default: backend/.venv)")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    interpreter = args.python or ROOT / "backend/.venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not interpreter.is_file():
        raise SystemExit("Backend interpreter not available; use --python")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    out = (args.output or ROOT / "tools/agent/reports" / stamp).resolve()
    out.mkdir(parents=True, exist_ok=False)
    cases = json.loads((ROOT / "agent/harness/cases.json").read_text(encoding="utf-8-sig"))
    results = []
    for case in cases:
        node = case["pytest"]
        if not node.startswith("backend/tests/test_agent.py::test_agent_") or ".." in node:
            raise ValueError("Harness test must belong to the registered agent test module")
        result = subprocess.run([str(interpreter), "-m", "pytest", node, "-q",
                                 "--basetemp", str(out / (case["id"] + "-temp")),
                                 "--junitxml", str(out / (case["id"] + ".xml"))],
                                cwd=ROOT, text=True, capture_output=True, check=False)
        (out / (case["id"] + ".txt")).write_text(result.stdout + result.stderr, encoding="utf-8")
        results.append({"id": case["id"], "exit_code": result.returncode,
                        "passed": result.returncode == 0, "provider": "controlled_fixture"})
        print(case["id"] + ": " + ("PASS" if result.returncode == 0 else "FAIL"), flush=True)
    report = {"cases": results, "passed": bool(results) and all(c["passed"] for c in results),
              "real_provider": "not_tested", "production_mutations": False}
    (out / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(str(out / "summary.json"))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
