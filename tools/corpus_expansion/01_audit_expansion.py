"""Read-only corpus audit. Run from the project root with python -m tools.corpus_expansion.audit_expansion."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import subprocess
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from pydantic import ValidationError

from backend.schema import Paper


def digest(data: bytes) -> str:
    """Return a SHA-256 hex digest of input bytes."""
    return hashlib.sha256(data).hexdigest()


def normalize(value: str) -> str:
    """Normalize Unicode, case and whitespace without fuzzy matching."""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    """Write a new UTF-8 CSV; never replace an existing file."""
    with path.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def audit(args: argparse.Namespace) -> dict:
    """Validate two deliveries and new PDFs; return summary, writing new reports only.

    Raises OSError/ValueError for unreadable sources or an existing output directory.
    Invalid records are reported rather than silently accepted.
    """
    output = args.output
    if output.exists():
        raise ValueError("output directory already exists; choose a new directory")
    issues: list[dict] = []
    provenance = {}

    def issue(batch: str, line: int, paper_id: str, code: str, severity: str = "error"):
        issues.append(
            {
                "batch": batch,
                "line": line,
                "paper_id": paper_id,
                "code": code,
                "severity": severity,
            }
        )

    def old_bytes(local: Path | None, name: str) -> bytes:
        if local:
            return local.read_bytes()
        if not args.old_git_ref:
            raise ValueError("provide old local files or --old-git-ref")
        return subprocess.run(
            ["git", "show", f"{args.old_git_ref}:data/paper_jsonl/{name}"],
            check=True,
            capture_output=True,
        ).stdout

    sources = {
        "old": (
            old_bytes(args.old_jsonl, "papers_final.jsonl"),
            old_bytes(args.old_manifest, "paper_source_manifest.csv"),
        ),
        "new": (args.new_jsonl.read_bytes(), args.new_manifest.read_bytes()),
    }
    batches = {}
    manifests = {}
    for batch, (raw, manifest_raw) in sources.items():
        provenance[batch] = {
            "jsonl_sha256": digest(raw),
            "manifest_sha256": digest(manifest_raw),
        }
        reader = csv.DictReader(io.StringIO(manifest_raw.decode("utf-8-sig")))
        if not {"paper_id", "source_file", "pdf_path", "pdf_sha256"}.issubset(
            reader.fieldnames or []
        ):
            raise ValueError(f"{batch}: missing manifest columns")
        manifest = list(reader)
        by_id = defaultdict(list)
        for row in manifest:
            by_id[row["paper_id"]].append(row)
            if not re.fullmatch(r"[0-9a-fA-F]{64}", row["pdf_sha256"] or ""):
                issue(batch, 0, row["paper_id"], "invalid_pdf_sha256")
        for pid, rows in by_id.items():
            if len(rows) != 1:
                issue(batch, 0, pid, "duplicate_manifest_id")
        records = []
        input_count = 0
        for line, text in enumerate(raw.decode("utf-8-sig").splitlines(), 1):
            if not text.strip():
                issue(batch, line, "", "blank_line", "warning")
                continue
            input_count += 1
            try:
                paper = Paper.model_validate(json.loads(text))
            except (ValueError, ValidationError, TypeError):
                issue(batch, line, "", "invalid_json_or_schema")
                continue
            record = paper.model_dump()
            record["line"] = line
            rows = by_id.get(paper.paper_id, [])
            row = rows[0] if len(rows) == 1 else {}
            record["pdf_sha256"] = row.get("pdf_sha256", "").lower()
            if not row or any(
                row.get(f) != record[f] for f in ("source_file", "pdf_path")
            ):
                issue(batch, line, paper.paper_id, "manifest_mismatch")
            if paper.paper_id.startswith("mock-"):
                issue(batch, line, paper.paper_id, "mock_in_real_delivery")
            if paper.parse_status == "error":
                issue(batch, line, paper.paper_id, "parse_error")
            if (
                "\ufffd" in paper.fulltext
                or "unreadable_characters_in_fulltext" in paper.errors
            ):
                issue(
                    batch,
                    line,
                    paper.paper_id,
                    "body_quarantined_by_existing_importer",
                    "warning",
                )
            records.append(record)
        record_ids = {r["paper_id"] for r in records}
        for pid in by_id.keys() - record_ids:
            issue(batch, 0, pid, "manifest_without_valid_record")
        expected = getattr(args, f"expected_{batch}")
        if input_count != expected:
            issue(batch, 0, "", "unexpected_record_count")
        provenance[batch].update(
            input_records=input_count,
            valid_records=len(records),
            manifest_rows=len(manifest),
        )
        batches[batch] = records
        manifests[batch] = by_id

    duplicates = []
    kinds = {
        "paper_id": lambda r: r["paper_id"],
        "pdf_sha256": lambda r: r["pdf_sha256"],
        "normalized_title": lambda r: normalize(r["title"]),
        "normalized_fulltext": lambda r: (
            digest(normalize(r["fulltext"]).encode()) if r["fulltext"].strip() else ""
        ),
    }
    for kind, key in kinds.items():
        indexes = {}
        for batch, records in batches.items():
            index = defaultdict(list)
            for record in records:
                value = key(record)
                if value:
                    index[value].append(record)
            indexes[batch] = index
        for batch, index in indexes.items():
            for value, records in index.items():
                if len(records) > 1:
                    for other in records[1:]:
                        duplicates.append(
                            {
                                "scope": f"within_{batch}",
                                "kind": kind,
                                "old_id": records[0]["paper_id"],
                                "new_id": other["paper_id"],
                                "old_line": records[0]["line"],
                                "new_line": other["line"],
                                "title": other["title"],
                            }
                        )
                        if kind == "paper_id":
                            issue(
                                batch,
                                other["line"],
                                other["paper_id"],
                                "duplicate_jsonl_id",
                            )
        for value in indexes["old"].keys() & indexes["new"].keys():
            for old in indexes["old"][value]:
                for new in indexes["new"][value]:
                    duplicates.append(
                        {
                            "scope": "cross_batch",
                            "kind": kind,
                            "old_id": old["paper_id"],
                            "new_id": new["paper_id"],
                            "old_line": old["line"],
                            "new_line": new["line"],
                            "title": new["title"],
                        }
                    )

    root = args.pdf_root.resolve(strict=True)
    pdf_checks = []
    for record in batches["new"]:
        name = record["source_file"]
        status = "verified"
        actual = ""
        if not name or any(c in name for c in "/\\:") or name in (".", ".."):
            status = "unsafe_source_file"
        else:
            candidate = (root / name).resolve()
            if not candidate.is_relative_to(root) or candidate.suffix.lower() != ".pdf":
                status = "unsafe_pdf_path"
            elif not candidate.is_file():
                status = "missing"
            else:
                try:
                    with candidate.open("rb") as stream:
                        signature = stream.read(5)
                        stream.seek(0)
                        actual = hashlib.file_digest(stream, "sha256").hexdigest()
                    if signature != b"%PDF-":
                        status = "invalid_pdf_signature"
                    elif actual != record["pdf_sha256"]:
                        status = "hash_mismatch"
                except OSError:
                    status = "unreadable"
        if status != "verified":
            issue("new", record["line"], record["paper_id"], f"pdf_{status}")
        pdf_checks.append(
            {
                "paper_id": record["paper_id"],
                "source_file": name,
                "status": status,
                "expected_sha256": record["pdf_sha256"],
                "actual_sha256": actual,
            }
        )

    cross = [r for r in duplicates if r["scope"] == "cross_batch"]
    summary = {
        "provenance": provenance,
        "old_git_ref": args.old_git_ref,
        "cross_batch_matches": {
            kind: {
                "pairs": sum(r["kind"] == kind for r in cross),
                "new_records": len({r["new_line"] for r in cross if r["kind"] == kind}),
            }
            for kind in kinds
        },
        "within_batch_matches": dict(
            Counter(
                f"{r['scope']}:{r['kind']}"
                for r in duplicates
                if r["scope"] != "cross_batch"
            )
        ),
        "parse_status": {
            batch: dict(Counter(r["parse_status"] or "unknown" for r in records))
            for batch, records in batches.items()
        },
        "pdf_status": dict(Counter(r["status"] for r in pdf_checks)),
        "pdf_files_on_disk": sum(
            p.is_file() for p in root.rglob("*") if p.suffix.lower() == ".pdf"
        ),
        "errors": sum(r["severity"] == "error" for r in issues),
        "warnings": sum(r["severity"] == "warning" for r in issues),
        "limitations": [
            "Old PDF bytes are not rechecked; cross-batch PDF equality uses source-manifest hashes.",
            "Title/body equality indicates candidates for review, not automatic deletion.",
            "No merge, indexing, or live service verification performed.",
        ],
    }
    output.mkdir(parents=True, exist_ok=False)
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# 论文扩容只读校验结果",
        "",
        f"旧库有效记录：{len(batches['old'])}；新库有效记录：{len(batches['new'])}。",
        "",
        "## 跨批重复检查",
        "",
    ]
    for kind, counts in summary["cross_batch_matches"].items():
        lines.append(
            f"- {kind}：{counts['new_records']} 条新增记录匹配旧库（{counts['pairs']} 对）。"
        )
    lines.extend(
        [
            "",
            f"PDF核验：{summary['pdf_status']}。",
            f"阻断问题：{summary['errors']}；警告：{summary['warnings']}。",
            "",
            "标题/正文匹配仅为疑似重复。旧PDF哈希来自固定版本来源清单，本次未重读旧PDF。",
            "详见 duplicates.csv、issues.csv、pdf_checks.csv；本次未合并或导入索引。",
        ]
    )
    (output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_csv(
        output / "duplicates.csv",
        duplicates,
        ["scope", "kind", "old_id", "new_id", "old_line", "new_line", "title"],
    )
    write_csv(
        output / "issues.csv", issues, ["batch", "line", "paper_id", "code", "severity"]
    )
    write_csv(
        output / "pdf_checks.csv",
        pdf_checks,
        ["paper_id", "source_file", "status", "expected_sha256", "actual_sha256"],
    )
    return summary


def main() -> int:
    """Parse explicit source/output paths; return 2 when the completed audit has errors."""
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("new-jsonl", "new-manifest", "pdf-root", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--old-jsonl", type=Path)
    parser.add_argument("--old-manifest", type=Path)
    parser.add_argument("--old-git-ref")
    parser.add_argument("--expected-old", type=int, default=859)
    parser.add_argument("--expected-new", type=int, default=3141)
    args = parser.parse_args()
    summary = audit(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 2 if summary["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
