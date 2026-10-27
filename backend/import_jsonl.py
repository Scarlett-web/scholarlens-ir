"""Validate JSONL, bulk-load a new generation, then atomically publish an alias."""

import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys
import uuid

from elasticsearch.helpers import streaming_bulk

from backend.config import Settings, make_client
from backend.mapping import index_definition
from backend.schema import Paper, SEARCH_FIELDS


def load_jsonl(path: Path, data_status: str) -> tuple[list[dict], dict]:
    """Validate the whole input before ES changes; return accepted records and audit counts.

    Raises ValueError on malformed JSON/schema, duplicate IDs or mixed Mock/real input.
    Parser error records are quarantined rather than indexed.
    """
    records = []
    seen = set()
    parser_counts = Counter({"success": 0, "partial": 0, "failed": 0, "unknown": 0})
    completeness = Counter()
    skipped = []
    body_quarantined = []
    input_count = 0
    raw = path.read_bytes()
    for line_number, line in enumerate(raw.decode("utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        input_count += 1
        try:
            paper = Paper.model_validate(json.loads(line))
        except (ValueError, TypeError) as exc:
            raise ValueError(f"line {line_number}: invalid JSON or paper schema") from exc
        if paper.paper_id in seen:
            raise ValueError(f"line {line_number}: duplicate paper_id")
        seen.add(paper.paper_id)
        is_mock = paper.paper_id.startswith("mock-")
        if is_mock != (data_status == "mock"):
            raise ValueError(f"line {line_number}: ID conflicts with --data-status")
        parser_counts[
            "failed" if paper.parse_status == "error" else paper.parse_status or "unknown"
        ] += 1
        if paper.parse_status == "error":
            skipped.append(
                {"line": line_number, "paper_id": paper.paper_id, "reason": "parse_error"}
            )
            continue
        doc = paper.index_document()
        if "unreadable_characters_in_fulltext" in paper.errors or (
            paper.fulltext and not doc["fulltext"]
        ):
            body_quarantined.append({"line": line_number, "paper_id": paper.paper_id})
        for key in (*SEARCH_FIELDS, "abstract", "year"):
            value = doc.get(key)
            nonempty = (
                any(x.strip() for x in value)
                if isinstance(value, list)
                else bool(value.strip())
                if isinstance(value, str)
                else value is not None
            )
            completeness[key] += bool(nonempty)
        records.append(doc)
    if not records:
        raise ValueError("no indexable records; active alias preserved")
    metadata = {
        "data_status": data_status,
        "input_sha256": hashlib.sha256(raw).hexdigest(),
        "input_records": input_count,
        "accepted_records": len(records),
        "parser": dict(parser_counts),
        "fields_completeness": {
            key: round(completeness[key] / len(records), 6)
            for key in (*SEARCH_FIELDS, "abstract", "year")
        },
        "skipped": skipped,
        "body_quarantined": body_quarantined,
    }
    return records, metadata


def publish_alias(client, alias: str, generation: str, previous: list[str]) -> None:
    """Atomically replace only the requested alias; keep all previous index data."""
    actions = [{"remove": {"index": name, "alias": alias}} for name in previous]
    actions.append({"add": {"index": generation, "alias": alias}})
    client.indices.update_aliases(actions=actions)


def import_records(client, alias: str, records: list[dict], metadata: dict) -> dict:
    """Stage and verify a generation; publish only after every bulk action succeeds."""
    if not re.fullmatch(r"scholarlens-[a-z0-9-]+", alias):
        raise ValueError(
            "alias must start scholarlens- and contain lowercase letters/digits/hyphens"
        )
    expected_suffix = "-mock" if metadata["data_status"] == "mock" else "-real"
    if not alias.endswith(expected_suffix):
        raise ValueError(f"alias must end with {expected_suffix}")
    previous = (
        list(client.indices.get_alias(name=alias))
        if client.indices.exists_alias(name=alias)
        else []
    )
    if not previous and client.indices.exists(index=alias):
        raise ValueError("requested alias already exists as a concrete index")
    built_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    generation = f"{alias}-{uuid.uuid4().hex[:12]}"
    metadata = {**metadata, "last_built_at": built_at}
    client.indices.create(index=generation, **index_definition(metadata))
    actions = (
        {"_op_type": "create", "_index": generation, "_id": doc["paper_id"], "_source": doc}
        for doc in records
    )
    failures = []
    indexed = 0
    for ok, item in streaming_bulk(
        client, actions, chunk_size=100, max_retries=2, raise_on_error=False
    ):
        if ok:
            indexed += 1
        else:
            action = next(iter(item.values()))
            failures.append({"id": action.get("_id"), "status": action.get("status")})
    client.indices.refresh(index=generation)
    actual = client.count(index=generation)["count"]
    if failures or indexed != len(records) or actual != len(records):
        raise ValueError(
            f"bulk import failed; active alias preserved; staged index={generation}; failures={len(failures)}"
        )
    publish_alias(client, alias, generation, previous)
    return {
        **metadata,
        "alias": alias,
        "generation": generation,
        "previous_generations": previous,
        "indexed": actual,
        "bulk_failed": len(failures),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--data-status", choices=("mock", "real"), required=True)
    parser.add_argument("--index", default=Settings.from_env().index)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.input.resolve() == args.report.resolve() or args.report.exists():
        parser.error("report must be a new path different from input")
    records, metadata = load_jsonl(args.input, args.data_status)
    # Reserve the report path before publishing so a missing/writable directory fails early.
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("x", encoding="utf-8") as report_file:
        try:
            with make_client(Settings(url=Settings.from_env().url, index=args.index)) as client:
                report = import_records(client, args.index, records, metadata)
        except Exception as exc:
            json.dump(
                {**metadata, "outcome": "failed", "error_type": type(exc).__name__},
                report_file,
                ensure_ascii=False,
                indent=2,
            )
            report_file.write("\n")
            raise
        json.dump(report, report_file, ensure_ascii=False, indent=2)
        report_file.write("\n")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"Import failed ({type(exc).__name__}): {exc}", file=sys.stderr)
        sys.exit(1)
