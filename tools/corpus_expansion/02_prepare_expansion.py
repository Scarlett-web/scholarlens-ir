"""Prepare a traceable merged corpus without changing sources or live indexes."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

from backend.schema import Paper


def sha256(data: bytes) -> str:
    """Return the SHA-256 of exact source/output bytes."""
    return hashlib.sha256(data).hexdigest()


def csv_bytes(rows: list[dict], fields: list[str]) -> bytes:
    """Serialize a spreadsheet-readable UTF-8 CSV with explicit columns."""
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8-sig")


def prepare(args: argparse.Namespace) -> dict:
    """Validate audited sources and write a new merged directory.

    Raises ValueError for stale audits, conflicts or existing output. Raises OSError
    for unreadable sources. No files are written until all data checks pass.
    """
    if args.output.exists():
        raise ValueError("output already exists; choose a new directory")
    report_raw = (args.audit_dir / "summary.json").read_bytes()
    audit = json.loads(report_raw)
    if audit.get("errors") != 0:
        raise ValueError("audit has blocking errors or lacks an error count")

    def old_source(path: Path | None, name: str) -> bytes:
        if path:
            return path.read_bytes()
        if not args.old_git_ref:
            raise ValueError("provide --old-git-ref or both old source paths")
        return subprocess.run(
            ["git", "show", f"{args.old_git_ref}:data/paper_jsonl/{name}"],
            check=True,
            capture_output=True,
        ).stdout

    inputs = {
        "old": (
            old_source(args.old_jsonl, "papers_final.jsonl"),
            old_source(args.old_manifest, "paper_source_manifest.csv"),
        ),
        "new": (args.new_jsonl.read_bytes(), args.new_manifest.read_bytes()),
    }
    all_ids: set[str] = set()
    old_pdf_hashes: set[str] = set()
    merged, manifest_rows, ledger = [], [], []
    provenance = {}
    status_counts: Counter = Counter()
    quarantine_counts: Counter = Counter()
    for batch, (raw, manifest_raw) in inputs.items():
        hashes = {"jsonl_sha256": sha256(raw), "manifest_sha256": sha256(manifest_raw)}
        previous = audit["provenance"][batch]
        if any(previous.get(key) != value for key, value in hashes.items()):
            raise ValueError(f"{batch}: sources differ from audited bytes")
        reader = csv.DictReader(io.StringIO(manifest_raw.decode("utf-8-sig")))
        fields = ["paper_id", "source_file", "pdf_path", "pdf_sha256"]
        if not set(fields).issubset(reader.fieldnames or []):
            raise ValueError(f"{batch}: missing manifest columns")
        rows = list(reader)
        by_id = {row["paper_id"]: row for row in rows}
        if len(rows) != len(by_id):
            raise ValueError(f"{batch}: duplicate manifest ID")
        batch_ids: set[str] = set()
        for source_line, text in enumerate(raw.decode("utf-8-sig").splitlines(), 1):
            if not text.strip():
                continue
            record = json.loads(text)
            paper = Paper.model_validate(record)
            pid = paper.paper_id
            if (
                pid in all_ids
                or pid.startswith("mock-")
                or paper.parse_status == "error"
            ):
                raise ValueError(
                    f"{batch} line {source_line}: duplicate/mock/error record"
                )
            row = by_id.get(pid)
            if not row or any(
                row[field] != record.get(field, "")
                for field in ("source_file", "pdf_path")
            ):
                raise ValueError(f"{batch} line {source_line}: manifest mismatch")
            pdf_hash = row["pdf_sha256"].lower()
            if not re.fullmatch(r"[0-9a-f]{64}", pdf_hash):
                raise ValueError(f"{batch} line {source_line}: invalid PDF hash")
            if batch == "new" and pdf_hash in old_pdf_hashes:
                raise ValueError("cross-batch PDF hash conflict requires review")
            if batch == "old":
                old_pdf_hashes.add(pdf_hash)
            all_ids.add(pid)
            batch_ids.add(pid)
            # Serialize original objects, preserving fields, values and stable IDs.
            merged.append(record)
            manifest_rows.append(
                {**{field: row[field] for field in fields}, "source_batch": batch}
            )
            quarantine = bool(
                "\ufffd" in paper.fulltext
                or "unreadable_characters_in_fulltext" in paper.errors
            )
            quarantine_counts[batch] += quarantine
            status_counts[paper.parse_status or "unknown"] += 1
            ledger.append(
                {
                    "merged_line": len(merged),
                    "source_batch": batch,
                    "source_line": source_line,
                    "paper_id": pid,
                    "source_file": paper.source_file,
                    "action": "retain_unchanged",
                    "body_policy": "quarantine_on_import"
                    if quarantine
                    else "existing_import_rules",
                    "record_sha256": sha256(
                        json.dumps(record, ensure_ascii=False, sort_keys=True).encode()
                    ),
                }
            )
        if batch_ids != set(by_id) or len(batch_ids) != getattr(
            args, f"expected_{batch}"
        ):
            raise ValueError(f"{batch}: record count or manifest coverage mismatch")
        if previous.get("valid_records") != len(batch_ids):
            raise ValueError(f"{batch}: audited count mismatch")
        provenance[batch] = {**hashes, "records": len(batch_ids)}

    payloads = {
        "merged_papers.jsonl": (
            "\n".join(
                json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in merged
            )
            + "\n"
        ).encode(),
        "merged_source_manifest.csv": csv_bytes(
            manifest_rows,
            ["paper_id", "source_file", "pdf_path", "pdf_sha256", "source_batch"],
        ),
        "preparation_ledger.csv": csv_bytes(
            ledger,
            [
                "merged_line",
                "source_batch",
                "source_line",
                "paper_id",
                "source_file",
                "action",
                "body_policy",
                "record_sha256",
            ],
        ),
    }
    summary = {
        "status": "prepared_only",
        "records": len(merged),
        "unique_ids": len(all_ids),
        "manifest_rows": len(manifest_rows),
        "ledger_rows": len(ledger),
        "inputs": provenance,
        "old_git_ref": args.old_git_ref,
        "audit_summary_sha256": sha256(report_raw),
        "parse_status": dict(status_counts),
        "quarantine_on_import": dict(quarantine_counts),
        "replaced_records": 0,
        "dropped_records": 0,
        "record_values_changed": 0,
        "outputs": {
            name: {"sha256": sha256(data), "bytes": len(data)}
            for name, data in payloads.items()
        },
        "limitations": [
            "PDF bytes are not rechecked in stage 02; stage 01 audit is reused.",
            "Original pdf_path values retained; two-root PDF mapping still needs configuration.",
            "Title/body candidates retained for review; no automatic deduplication.",
            "No ES import, vector build, application change, push or deployment.",
        ],
    }
    payloads["summary.json"] = (
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    ).encode()
    payloads["summary.md"] = (
        f"# 02 论文合并准备结果\n\n旧库 {provenance['old']['records']} + 新库 {provenance['new']['records']} = {len(merged)} 条。\n\n"
        f"唯一ID、来源清单、逐条账本均为 {len(merged)} 条。\n\n"
        f"正文警告：旧库 {quarantine_counts['old']}、新库 {quarantine_counts['new']}；只登记导入时隔离策略，本文件保留原正文。\n\n"
        "所有原字段值、ID和pdf_path保留；未替换论文、未删除同标题项。JSON序列化格式可与原件不同。\n\n"
        "输入哈希与01报告一致。旧库来自固定来源；输入原件未写入。PDF核验沿用01报告，本次未重读PDF。\n\n"
        "尚未导入索引、构建向量或配置两批PDF根目录。源码与线上应用未更新。\n"
    ).encode()
    args.output.mkdir(parents=True, exist_ok=False)
    for name, data in payloads.items():
        with (args.output / name).open("xb") as stream:
            stream.write(data)
    return summary


def main() -> int:
    """Read CLI inputs and print the prepared-corpus summary."""
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("new-jsonl", "new-manifest", "audit-dir", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--old-jsonl", type=Path)
    parser.add_argument("--old-manifest", type=Path)
    parser.add_argument("--old-git-ref")
    parser.add_argument("--expected-old", type=int, default=859)
    parser.add_argument("--expected-new", type=int, default=3141)
    print(json.dumps(prepare(parser.parse_args()), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
