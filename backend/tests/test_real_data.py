"""Full-delivery audit and real HTTP/ES regression, explicitly enabled with data path."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid

from elasticsearch import Elasticsearch
import httpx
import pytest

from backend.import_jsonl import import_records, load_jsonl
from backend.prepare_real_data import audit_delivery, prepare, save_new
from backend.real_data_checks1 import select_representatives, verify_index

pytestmark = [pytest.mark.integration, pytest.mark.real_data]


@pytest.fixture(scope="module")
def delivery(request):
    configured = request.config.getoption("--real-data-dir")
    if not configured:
        pytest.skip("real delivery is external; pass --real-data-dir explicitly")
    root = Path(configured)
    raw = root / "papers_final.jsonl"
    manifest = root / "paper_source_manifest.csv"
    ready = root / "papers_index_ready.jsonl"
    for path in (
        raw,
        manifest,
        ready,
        root / "real_data_quality_report.json",
        root / "real_data_changes.json",
    ):
        assert path.is_file(), path.name
    records, report, edits = audit_delivery(raw, manifest, Path.cwd(), root / "pdfXML")
    return {
        "root": root,
        "raw": raw,
        "manifest": manifest,
        "ready": ready,
        "records": records,
        "audit": report,
        "edits": edits,
    }


def test_full_jsonl_schema_manifest_and_formal_ids(delivery):
    report = delivery["audit"]
    assert report["utf8_valid"] and not report["fatal_issues"]
    assert (
        report["schema_valid_records"] == report["unique_ids"] == report["manifest_records"] == 859
    )
    assert report["duplicate_records"] == 0 and report["blank_lines"] == []
    assert report["status_counts"] == {"success": 215, "partial": 644, "error": 0}
    assert report["untraceable_records"] == 0 and report["pdf_present"] == 0
    assert all(r["paper_id"].startswith("source-sha256:") for r in delivery["records"])


def test_ready_matches_original_except_logged_bodies(delivery):
    root = delivery["root"]
    ready = [
        json.loads(line) for line in delivery["ready"].read_text(encoding="utf-8").splitlines()
    ]
    ledger = json.loads((root / "real_data_changes.json").read_text(encoding="utf-8"))
    ids = {change["paper_id"] for change in ledger}
    assert len(ids) == len(ledger) == 4
    assert len(ready) == len(delivery["records"])
    for original, cleaned in zip(delivery["records"], ready, strict=True):
        assert original["paper_id"] == cleaned["paper_id"]
        expected = {**original, "fulltext": ""} if original["paper_id"] in ids else original
        assert cleaned == expected
    report = json.loads((root / "real_data_quality_report.json").read_text(encoding="utf-8"))
    assert hashlib.sha256(delivery["raw"].read_bytes()).hexdigest() == report["input_sha256"]
    assert (
        hashlib.sha256(delivery["ready"].read_bytes()).hexdigest() == report["index_ready_sha256"]
    )
    assert report["index_body_nonempty"] == 855


def test_preparation_reproducible_and_no_overwrite(delivery, tmp_path):
    prepare(
        delivery["raw"],
        delivery["manifest"],
        tmp_path / "ready.jsonl",
        tmp_path / "report.json",
        tmp_path / "edits.json",
        Path.cwd(),
        delivery["root"] / "pdfXML",
    )
    assert (tmp_path / "ready.jsonl").read_bytes() == delivery["ready"].read_bytes()
    assert (tmp_path / "report.json").read_bytes() == (
        delivery["root"] / "real_data_quality_report.json"
    ).read_bytes()
    protected = tmp_path / "protected.txt"
    protected.write_bytes(b"original")
    with pytest.raises(ValueError, match="preserved"):
        save_new(protected, b"replacement")
    assert protected.read_bytes() == b"original"


def test_representative_selection_covers_edges(delivery):
    ready = [
        json.loads(line) for line in delivery["ready"].read_text(encoding="utf-8").splitlines()
    ]
    selected, reasons = select_representatives(ready)
    assert len(selected) == len({r["paper_id"] for r in selected}) == 20
    labels = {label for entry in reasons for label in entry["reasons"]}
    assert {
        "complete_metadata",
        "missing_date_and_year",
        "year_only",
        "many_authors",
        "many_institutions",
        "missing_address",
        "missing_affiliation",
        "missing_authors",
        "missing_abstract",
        "body_quality_warning_metadata_retained",
    } <= labels
    assert sum("unreadable_characters_in_fulltext" in r["errors"] for r in selected) == 4


@pytest.fixture(scope="module")
def actual_acceptance(delivery, request):
    with Elasticsearch("http://127.0.0.1:9200", request_timeout=30) as client:
        return verify_index(
            client,
            request.config.getoption("--real-alias"),
            delivery["ready"],
            request.config.getoption("--real-api"),
        )


def test_all_imported_sources_and_count(actual_acceptance):
    assert actual_acceptance["all_sources_exact"] == actual_acceptance["indexed"] == 859
    assert actual_acceptance["stats"]["status"] == "real"
    assert actual_acceptance["stats"]["parser"]["partial"] == 644


@pytest.mark.parametrize(
    "field", ["title", "authors", "date", "affiliation", "address", "fulltext", "all"]
)
def test_actual_http_six_fields_and_all(actual_acceptance, field):
    case = next(case for case in actual_acceptance["cases"] if case["field"] == field)
    assert case["http"] == 200 and case["total"] > 0 and case["expected_rank"] > 0
    assert case["first_result"]["score"] > 0


def test_actual_ranking_pagination_years_highlight_details_and_errors(actual_acceptance):
    checks = actual_acceptance["checks"]
    assert all(
        checks[field]
        for field in (
            "bm25",
            "pagination",
            "year_filter",
            "year_sort",
            "empty_result",
            "invalid_parameters",
            "paper_not_found",
        )
    )
    assert len(checks["body_quarantine"]) == 4
    assert len(actual_acceptance["details"]) == 20
    assert all(d["fields_exact"] and d["pdf_http"] == 404 for d in actual_acceptance["details"])


def test_mock_and_real_remain_isolated(delivery, request):
    # Own the synthetic fixture; do not assume or replace a shared mock alias.
    mock_alias = f"scholarlens-isolation-{uuid.uuid4().hex[:8]}-mock"
    docs, metadata = load_jsonl(Path("data/sample/mock_papers.jsonl"), "mock")
    with Elasticsearch("http://127.0.0.1:9200", request_timeout=30) as client:
        import_records(client, mock_alias, docs, metadata)
        assert client.count(index=mock_alias)["count"] == 2
        assert client.count(index=request.config.getoption("--real-alias"))["count"] == 859
        assert not client.exists(index=request.config.getoption("--real-alias"), id="mock-0002")
        assert not client.exists(
            index=mock_alias, id=delivery["records"][0]["paper_id"]
        )


def test_real_generation_rollback_cli_preserves_both_generations(delivery, tmp_path):
    # Own new alias only: no delete calls and no mutation of business aliases.
    alias = f"scholarlens-rollback-{uuid.uuid4().hex[:8]}-real"
    docs, metadata = load_jsonl(delivery["root"] / "papers_real_sample20.jsonl", "real")
    with Elasticsearch("http://127.0.0.1:9200", request_timeout=30) as client:
        first = import_records(client, alias, docs, metadata)
        second = import_records(client, alias, docs, metadata)
        report = tmp_path / "import.json"
        report.write_text(json.dumps(second), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "-m", "backend.rollback_index", "--report", str(report)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert list(client.indices.get_alias(name=alias)) == [first["generation"]]
        assert client.indices.exists(index=first["generation"]) and client.indices.exists(
            index=second["generation"]
        )
        assert client.count(index=alias)["count"] == 20


def test_own_api_restart_preserves_real_index(delivery, request, tmp_path):
    """Restart only a test-created API on 8002; main APIs/ES remain running."""
    alias = request.config.getoption("--real-alias")
    start = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        "infra/start-backend1.ps1",
        "-Port",
        "8002",
        "-Index",
        alias,
    ]
    stop = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        "infra/stop-backend.ps1",
        "-Port",
        "8002",
    ]

    # A Windows daemon can inherit PIPE handles and hold communicate() open.
    # A regular logfile avoids waiting for background children to close the pipe.
    def start_owned():
        with (tmp_path / "api-start.log").open("ab") as log:
            result = subprocess.run(start, stdout=log, stderr=subprocess.STDOUT, timeout=90)
        assert result.returncode == 0, "inspect test api-start.log"

    start_owned()
    try:
        with httpx.Client(base_url="http://127.0.0.1:8002", timeout=15, trust_env=False) as api:
            before = api.get("/api/stats").json()
        stopped = subprocess.run(stop, capture_output=True, text=True)
        assert stopped.returncode == 0, stopped.stderr
        start_owned()
        with httpx.Client(base_url="http://127.0.0.1:8002", timeout=15, trust_env=False) as api:
            after = api.get("/api/stats").json()
            found = api.get("/api/papers/" + delivery["records"][0]["paper_id"])
        assert before == after and after["status"] == "real" and after["indexed"] == 859
        assert found.status_code == 200
    finally:
        stopped = subprocess.run(stop, capture_output=True, text=True)
        assert stopped.returncode == 0, stopped.stderr
