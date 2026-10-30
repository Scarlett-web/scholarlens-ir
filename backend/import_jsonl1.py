"""Build an isolated expansion BM25 index using the existing importer."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
from urllib.request import urlopen
from urllib.parse import urlparse

from backend.schema import Paper

OUTPUT = Path("output/corpus-expansion/index-04")
PAPERS = "scholarlens-papers-expansion-real"
VECTORS = "scholarlens-vectors-expansion-real"


def validate_url(url: str) -> None:
    """Keep this local-only stage away from remote or production clusters."""
    parsed = urlparse(url)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in ("127.0.0.1", "localhost", "::1")
        or parsed.username
        or parsed.password
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("only a local loopback Elasticsearch URL is allowed")


def validate_alias(alias: str, vector: bool = False) -> None:
    """Reject protected base aliases and unrelated namespaces before any mutation."""
    pattern = (
        r"scholarlens-vectors-expansion[a-z0-9-]*-real"
        if vector
        else r"scholarlens-papers-expansion[a-z0-9-]*-real"
    )
    if not re.fullmatch(pattern, alias):
        raise ValueError("use an isolated expansion alias ending -real")


def save_report(path: Path, report: dict) -> None:
    """Write a fresh report, rejecting accidental replacement of previous evidence."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def check_input(path: Path, summary_path: Path, expected: int) -> dict:
    """Check prepared bytes and count with the unchanged backend schema."""
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if summary["outputs"]["merged_papers.jsonl"]["sha256"] != digest:
        raise ValueError("input differs from stage 02 output")
    seen = set()
    for text in raw.decode("utf-8-sig").splitlines():
        if not text.strip():
            continue
        paper = Paper.model_validate(json.loads(text))
        if (
            paper.paper_id in seen
            or paper.paper_id.startswith("mock-")
            or paper.parse_status == "error"
        ):
            raise ValueError("duplicate/mock/error record in expansion input")
        seen.add(paper.paper_id)
    if len(seen) != expected or summary["records"] != expected:
        raise ValueError("prepared corpus count mismatch")
    return {"input_sha256": digest, "records": len(seen)}


def dependencies(url: str, vector: bool = False, model_dir: Path | None = None) -> dict:
    """Return explicit local dependency status without downloading or starting services."""
    modules = ["elasticsearch"] + (
        ["filelock", "onnxruntime", "tokenizers", "httpx", "numpy"] if vector else []
    )
    missing = [name for name in modules if importlib.util.find_spec(name) is None]
    info = {}
    try:
        with urlopen(url, timeout=3) as response:
            info = json.load(response)
        es_ready = (
            info.get("version", {}).get("number") == "8.19.23"
            and info.get("cluster_name") == "scholarlens-local"
        )
    except (OSError, ValueError):
        es_ready = False
    model_ready = not vector or bool(
        model_dir
        and all(
            (model_dir / name).is_file()
            for name in (
                "manifest.json",
                "model.onnx",
                "tokenizer.json",
                "pooling.json",
                "sentence_bert_config.json",
            )
        )
    )
    return {
        "ready": not missing and es_ready and model_ready,
        "missing_python_modules": missing,
        "elasticsearch_ready": es_ready,
        "model_files_present": model_ready,
    }


def main() -> int:
    """Validate inputs and invoke the original generation-based importer."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, default=Path("output/corpus-expansion/prepare-02/merged_papers.jsonl")
    )
    parser.add_argument(
        "--prepare-summary",
        type=Path,
        default=Path("output/corpus-expansion/prepare-02/summary.json"),
    )
    parser.add_argument("--index", default=PAPERS)
    parser.add_argument("--url", default="http://127.0.0.1:9200")
    parser.add_argument("--expected-count", type=int, default=4000)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    validate_url(args.url)
    validate_alias(args.index)
    path = args.report or OUTPUT / (
        "keyword-preflight.json" if args.dry_run else "keyword-report.json"
    )
    if path.exists():
        raise ValueError("report exists; choose a new path")
    evidence = check_input(args.input, args.prepare_summary, args.expected_count)
    deps = dependencies(args.url)
    report = {
        **evidence,
        "alias": args.index,
        "dependencies": deps,
        "status": "preflight_ready" if deps["ready"] else "dependency_not_ready",
    }
    if args.dry_run or not deps["ready"]:
        save_report(path, report)
        print(json.dumps(report, indent=2))
        return 0 if deps["ready"] else 2
    from backend.config import Settings, make_client
    from backend.import_jsonl import import_records, load_jsonl

    records, metadata = load_jsonl(args.input, "real")
    with make_client(Settings(url=args.url, index=args.index)) as client:
        report = import_records(client, args.index, records, metadata)
    report["status"] = "ready"
    save_report(path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
