"""Build matching expansion vectors with the original resumable vector builder."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path

from backend.import_jsonl1 import (
    OUTPUT,
    PAPERS,
    VECTORS,
    dependencies,
    save_report,
    validate_alias,
    validate_url,
)


def main() -> int:
    """Check the exact keyword generation, build vectors, and emit local config."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", default=PAPERS)
    parser.add_argument("--vector-index", default=VECTORS)
    parser.add_argument("--url", default="http://127.0.0.1:9200")
    parser.add_argument("--model-dir", type=Path, default=Path("backend/.runtime/minilm"))
    parser.add_argument("--keyword-report", type=Path, default=OUTPUT / "keyword-report.json")
    parser.add_argument("--state", type=Path, default=OUTPUT / "vector-state.json")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--batch-size", type=int, choices=range(1, 33), default=8)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=1)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    validate_url(args.url)
    validate_alias(args.index)
    validate_alias(args.vector_index, vector=True)
    path = args.report or OUTPUT / (
        "vector-preflight.json" if args.dry_run else "vector-report.json"
    )
    if path.exists():
        raise ValueError("report exists; choose a new path")
    deps = dependencies(args.url, vector=True, model_dir=args.model_dir)
    keyword = (
        json.loads(args.keyword_report.read_text(encoding="utf-8"))
        if args.keyword_report.is_file()
        else {}
    )
    keyword_ready = (
        keyword.get("status") == "ready"
        and keyword.get("alias") == args.index
        and keyword.get("indexed") == 4000
        and keyword.get("bulk_failed") == 0
    )
    if args.dry_run or not deps["ready"] or not keyword_ready:
        report = {
            "status": "preflight_ready"
            if deps["ready"] and keyword_ready
            else "dependency_not_ready",
            "dependencies": deps,
            "keyword_ready": keyword_ready,
            "base_alias": args.index,
            "vector_alias": args.vector_index,
        }
        save_report(path, report)
        print(json.dumps(report, indent=2))
        return 0 if deps["ready"] and keyword_ready else 2
    from backend.config import Settings, make_client
    from backend.embeddings import Encoder
    from backend.vector_index import build

    settings = replace(
        Settings.from_env(),
        url=args.url,
        index=args.index,
        vector_index=args.vector_index,
        model_dir=str(args.model_dir.resolve()),
    )
    with make_client(settings) as client:
        mappings = client.indices.get_mapping(index=args.index)
        if list(mappings) != [keyword["generation"]]:
            raise ValueError("base alias changed after keyword import")
        meta = mappings[keyword["generation"]]["mappings"]["_meta"]
        if (
            meta.get("input_sha256") != keyword["input_sha256"]
            or client.count(index=args.index)["count"] != 4000
        ):
            raise ValueError("base generation input/count mismatch")
    Encoder(settings.model_dir).encode(["expansion model verification"])
    state = build(settings, args.state, args.batch_size, args.workers)
    if (
        state["status"] != "ready"
        or state["identity"]["base_generation"] != keyword["generation"]
        or state["completed"] != state["identity"]["chunks"]
    ):
        raise ValueError("vector verification failed")
    from backend.verify_vectors import verify

    verification_path = path.with_name(path.stem + "-verification.json")
    verification = verify(settings, verification_path)
    if verification["base_generation"] != keyword["generation"]:
        raise ValueError("base alias changed during vector verification")
    save_report(path, state)
    config = path.parent / "local-index.env"
    if not config.exists():
        with config.open("x", encoding="utf-8") as stream:
            stream.write(f"ELASTICSEARCH_INDEX={args.index}\nVECTOR_INDEX={args.vector_index}\n")
    print(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
