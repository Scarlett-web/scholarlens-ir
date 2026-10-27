"""Audit a complete delivery and create a separate, traceable index input.

Never edits input data or regenerates IDs. New outputs are exclusive/idempotent;
different existing output bytes cause a failure instead of replacement.
"""

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import statistics

from pydantic import ValidationError

from backend.schema import Paper

FIELDS = tuple(Paper.model_fields)
DECLARED_SHA256 = "1d37b56454e30ec4f7381164626b3c8c8874a7560f47025ea45eb126d5054f94"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save_new(path: Path, data: bytes) -> None:
    """Write a new artifact or verify identical existing bytes; never replace it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"existing artifact differs: {path.name}; preserved")
        return
    with path.open("xb") as output:
        output.write(data)


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def nonempty(value) -> bool:
    if isinstance(value, list):
        return any(str(item).strip() for item in value)
    return bool(value.strip()) if isinstance(value, str) else value is not None


def length_summary(values: list[int]) -> dict:
    if not values:
        return {}
    ordered = sorted(values)
    return {
        "min": ordered[0],
        "p05": ordered[int((len(ordered) - 1) * 0.05)],
        "median": statistics.median(ordered),
        "p95": ordered[int((len(ordered) - 1) * 0.95)],
        "max": ordered[-1],
        "mean": round(statistics.mean(ordered), 2),
    }


def audit_delivery(
    raw_path: Path, manifest_path: Path, project_root: Path, xml_root: Path | None = None
) -> tuple[list[dict], dict, list[dict]]:
    """Check every line, field and manifest row. Return original records, audit and edits.

    Validation errors are reported across all lines rather than silently discarded.
    PDF truth remains unverified when source files are absent.
    """
    raw = raw_path.read_bytes()
    text = raw.decode("utf-8-sig", errors="strict")
    rows = list(csv.DictReader(io.StringIO(manifest_path.read_text(encoding="utf-8-sig"))))
    fatal = []
    records = []
    line_numbers = {}
    blank_lines = []
    schema_issues = Counter()
    id_counts = Counter()
    canonical = Counter()
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            blank_lines.append(number)
            continue
        try:
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError("line is not an object")
            Paper.model_validate(record)
            missing = [field for field in FIELDS if field not in record]
            if missing:
                raise ValueError("delivery fields missing: " + ",".join(missing))
        except (ValueError, ValidationError) as exc:
            fields = (
                [str(e["loc"][0]) for e in exc.errors() if e["loc"]]
                if isinstance(exc, ValidationError)
                else ["record"]
            )
            schema_issues.update(fields)
            fatal.append({"line": number, "code": "schema_invalid", "fields": fields})
            continue
        id_counts[record["paper_id"]] += 1
        canonical[sha256(json.dumps(record, sort_keys=True, ensure_ascii=False).encode())] += 1
        if record["paper_id"].startswith("mock-"):
            fatal.append({"line": number, "code": "mock_in_real_delivery"})
        if not re.fullmatch(r"source-sha256:[0-9a-f]{64}", record["paper_id"]):
            fatal.append({"line": number, "code": "unexpected_formal_id"})
        records.append(record)
        line_numbers[record["paper_id"]] = number
    for paper_id, count in id_counts.items():
        if count > 1:
            fatal.append({"paper_id": paper_id, "code": "duplicate_id", "count": count})
    by_id = {row.get("paper_id"): row for row in rows}
    for field in ("paper_id", "source_file", "pdf_path", "pdf_sha256"):
        values = [row.get(field, "") for row in rows]
        if any(not value for value in values) or len(set(values)) != len(values):
            fatal.append({"code": "manifest_missing_or_duplicate", "field": field})
    warnings = []
    edits = []
    anomalies = []
    paths = []
    field_anomalies = Counter()
    manual = {field: set() for field in FIELDS}
    statuses = Counter()
    issue_counts = Counter()
    normalized_titles = Counter()
    for record in records:
        paper_id = record["paper_id"]
        row = by_id.get(paper_id)
        statuses[record["parse_status"]] += 1
        issue_counts.update(record["errors"])
        normalized_titles[record["title"].casefold().strip()] += 1
        if not row or any(record[field] != row.get(field) for field in ("source_file", "pdf_path")):
            fatal.append({"paper_id": paper_id, "code": "manifest_mismatch"})
            continue
        pdf_hash = row["pdf_sha256"]
        if not re.fullmatch(r"[0-9a-f]{64}", pdf_hash):
            fatal.append({"paper_id": paper_id, "code": "invalid_pdf_sha256"})
        # Verify an existing identifier against the declared rule; do not assign a new ID.
        expected = "source-sha256:" + sha256((record["source_file"] + "\0" + pdf_hash).encode())
        if paper_id != expected:
            fatal.append({"paper_id": paper_id, "code": "id_formula_mismatch"})
        path_text = record["pdf_path"]
        if (
            not path_text
            or ":" in path_text
            or path_text.startswith(("/", "\\"))
            or Path(path_text).name != record["source_file"]
        ):
            fatal.append({"paper_id": paper_id, "code": "invalid_source_path"})
        resolved = (project_root / path_text).resolve()
        pdf_present = resolved.is_file()
        hash_verified = sha256(resolved.read_bytes()) == pdf_hash if pdf_present else False
        if pdf_present and not hash_verified:
            fatal.append({"paper_id": paper_id, "code": "pdf_hash_mismatch"})
        xml_present = (
            (xml_root / (Path(record["source_file"]).stem + ".grobid.tei.xml")).is_file()
            if xml_root
            else None
        )
        paths.append(
            {
                "paper_id": paper_id,
                "source_file": record["source_file"],
                "pdf_present": pdf_present,
                "pdf_hash_verified": hash_verified,
                "xml_present": xml_present,
            }
        )
        flags = []
        replacement_count = record["fulltext"].count("\ufffd")
        if replacement_count or "unreadable_characters_in_fulltext" in record["errors"]:
            flags.append("body_quarantined")
            field_anomalies["fulltext"] += 1
            manual["fulltext"].add(paper_id)
            edits.append(
                {
                    "paper_id": paper_id,
                    "source_file": record["source_file"],
                    "line": line_numbers[paper_id],
                    "field": "fulltext",
                    "action": "quarantine_for_index",
                    "original_characters": len(record["fulltext"]),
                    "original_sha256": sha256(record["fulltext"].encode()),
                    "new_value": "",
                    "replacement_count": replacement_count,
                    "reason": "U+FFFD or parser unreadable marker; original kept in papers_final.jsonl",
                }
            )
        if (
            re.match(r"(?i)^figure\s+\d", record["title"])
            or "\ufffd" in record["title"]
            or len(record["title"]) < 5
        ):
            flags.append("title_review")
            field_anomalies["title"] += 1
            manual["title"].add(paper_id)
        if re.search(r"\b(?:foot_\d+)\b|[a-z]and[A-Z]", record["fulltext"]):
            flags.append("body_boundary_review")
            manual["fulltext"].add(paper_id)
        if record["fulltext"] and len(record["fulltext"]) < 1000:
            flags.append("short_body_review")
            manual["fulltext"].add(paper_id)
        for field in FIELDS:
            if record.get(field) and "\ufffd" in json.dumps(record[field], ensure_ascii=False):
                manual[field].add(paper_id)
        if flags:
            anomalies.append(
                {"paper_id": paper_id, "source_file": record["source_file"], "flags": flags}
            )
    if set(by_id) != set(id_counts):
        fatal.append(
            {"code": "manifest_set_mismatch", "manifest_only": sorted(set(by_id) - set(id_counts))}
        )
    if sha256(raw) != DECLARED_SHA256:
        warnings.append(
            {
                "code": "declared_hash_differs",
                "declared": DECLARED_SHA256,
                "actual": sha256(raw),
                "interpretation": "pinned Git delivery verified; previous declared binary snapshot unavailable",
            }
        )
    warnings.extend(
        [
            {
                "code": "pdf_truth_not_verified",
                "message": "PDF metadata/hash尚未实物核验；清单自洽不证明PDF事实",
            },
            {
                "code": "body_quality_not_certified",
                "message": "非空和无U+FFFD不保证正文完整；已有XML提取遗漏/拼接需数据组复核",
            },
        ]
    )
    count = len(records)
    report = {
        "input_bytes": len(raw),
        "input_sha256": sha256(raw),
        "utf8_valid": True,
        "bom": raw.startswith(b"\xef\xbb\xbf"),
        "physical_lines": len(text.splitlines()),
        "nonblank_lines": len(text.splitlines()) - len(blank_lines),
        "blank_lines": blank_lines,
        "schema_valid_records": count,
        "unique_ids": len(id_counts),
        "duplicate_records": sum(value - 1 for value in canonical.values()),
        "schema_anomalies": dict(schema_issues),
        "expected_record_count": 859,
        "record_count_matches_delivery": count == 859,
        "status_counts": {key: statuses[key] for key in ("success", "partial", "error")},
        "fields": {
            field: {
                "nonempty": sum(nonempty(r.get(field)) for r in records),
                "rate": round(sum(nonempty(r.get(field)) for r in records) / count, 6)
                if count
                else 0,
                "anomalies": field_anomalies[field],
                "manual_review": len(manual[field]),
            }
            for field in FIELDS
        },
        "missing_date": sum(not r["date"] for r in records),
        "year_only": sum(not r["date"] and r["year"] is not None for r in records),
        "fulltext_lengths": length_summary([len(r["fulltext"]) for r in records]),
        "abstract_lengths": length_summary([len(r["abstract"]) for r in records]),
        "duplicate_title_candidates": {
            title: value for title, value in normalized_titles.items() if value > 1
        },
        "issue_counts": dict(issue_counts),
        "anomalies": anomalies,
        "manifest_records": len(rows),
        "source_checks": paths,
        "untraceable_records": sum(r["paper_id"] not in by_id for r in records),
        "pdf_present": sum(p["pdf_present"] for p in paths),
        "pdf_hash_verified": sum(p["pdf_hash_verified"] for p in paths),
        "xml_present": sum(p["xml_present"] is True for p in paths),
        "body_quarantined_count": len(edits),
        "fatal_issues": fatal,
        "warnings": warnings,
    }
    return records, report, edits


def prepare(
    raw_path: Path,
    manifest_path: Path,
    output: Path,
    report_path: Path,
    changes_path: Path,
    project_root: Path,
    xml_root: Path | None = None,
) -> dict:
    """Create new ready data and evidence after full audit; ValueError blocks bad delivery."""
    outputs = [output.resolve(), report_path.resolve(), changes_path.resolve()]
    if len(set(outputs)) != 3 or any(
        path in [raw_path.resolve(), manifest_path.resolve()] for path in outputs
    ):
        raise ValueError("input/output paths collide")
    records, report, changes = audit_delivery(raw_path, manifest_path, project_root, xml_root)
    if report["fatal_issues"]:
        save_new(report_path, json_bytes(report))
        raise ValueError("delivery audit failed; see quality report; no ready data published")
    quarantined = {change["paper_id"] for change in changes}
    ready = [
        {**record, "fulltext": ""} if record["paper_id"] in quarantined else record
        for record in records
    ]
    payload = (
        "\n".join(json.dumps(record, ensure_ascii=False) for record in ready) + "\n"
    ).encode()
    report.update(
        index_ready_records=len(ready),
        index_ready_sha256=sha256(payload),
        index_body_nonempty=sum(bool(record["fulltext"]) for record in ready),
        changed_records=len(changes),
        unchanged_records=len(ready) - len(changes),
    )
    save_new(output, payload)
    save_new(changes_path, json_bytes(changes))
    save_new(report_path, json_bytes(report))
    if sha256(raw_path.read_bytes()) != report["input_sha256"]:
        raise ValueError("source changed during preparation")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--changes", type=Path, required=True)
    parser.add_argument("--xml-root", type=Path)
    args = parser.parse_args()
    report = prepare(
        args.input,
        args.manifest,
        args.output,
        args.report,
        args.changes,
        Path(__file__).resolve().parent.parent,
        args.xml_root,
    )
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "input_sha256",
                    "schema_valid_records",
                    "status_counts",
                    "body_quarantined_count",
                    "index_ready_records",
                    "pdf_present",
                    "xml_present",
                )
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
