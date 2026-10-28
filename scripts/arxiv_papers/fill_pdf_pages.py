"""Fill physical PDF page counts in an existing arXiv JSONL file.

Run from the project root:
    python scripts/arxiv_papers/fill_pdf_pages.py \
        --jsonl scripts/arxiv_papers/papers_arxiv.jsonl \
        --pdf-dir "E:/FilePackage/information retrieval/KagglePDF/kaggle_papers_PDF"

Only ``pages``, the corresponding missing/error markers, and ``parse_status``
are updated. The original PDF files are read without modification.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PAGES_LINE = re.compile(r"^Pages:\s*(\d+)\s*$", re.MULTILINE)


def physical_page_count(pdf: Path) -> tuple[int | None, str | None]:
    """Return (page count, error); a failed or ambiguous PDF yields no count."""
    try:
        result = subprocess.run(
            ["pdfinfo", str(pdf)],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, type(exc).__name__
    if result.returncode != 0:
        return None, f"pdfinfo_exit_{result.returncode}"
    match = PAGES_LINE.search(result.stdout)
    if match is None or int(match.group(1)) < 1:
        return None, "invalid_page_count"
    return int(match.group(1)), None


def source_pdf(record: dict, pdf_dir: Path) -> Path:
    """Resolve a record's PDF and reject paths outside the expected directory."""
    relative = record.get("pdf_path")
    source_file = record.get("source_file")
    if not isinstance(relative, str) or not isinstance(source_file, str):
        raise ValueError("pdf_path and source_file must be strings")
    pdf = (PROJECT_ROOT / relative).resolve()
    if not pdf.is_relative_to(pdf_dir) or pdf.name != source_file or not pdf.is_file():
        raise ValueError(f"PDF mapping cannot be verified: {source_file}")
    return pdf


def fill_pages(jsonl: Path, pdf_dir: Path, workers: int) -> dict[str, int]:
    """Read all mapped PDFs and atomically update page counts in the JSONL."""
    pdf_dir = pdf_dir.resolve()
    pdfs: dict[str, Path] = {}
    records = 0
    with jsonl.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            record = json.loads(line)
            pdf = source_pdf(record, pdf_dir)
            if record.get("pages") is not None:
                raise ValueError(f"line {line_number}: pages already populated")
            if record["source_file"] in pdfs:
                raise ValueError(f"line {line_number}: repeated source_file")
            pdfs[record["source_file"]] = pdf
            records += 1

    with ThreadPoolExecutor(max_workers=workers) as pool:
        checked = dict(zip(pdfs, pool.map(physical_page_count, pdfs.values())))

    filled = 0
    unreadable = 0
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="\n", dir=jsonl.parent,
            prefix="pages_", suffix=".tmp", delete=False,
        ) as output:
            temp_path = Path(output.name)
            with jsonl.open("r", encoding="utf-8") as source:
                for line in source:
                    record = json.loads(line)
                    count, error = checked[record["source_file"]]
                    errors = record["errors"]
                    if count is None:
                        unreadable += 1
                        marker = f"pdf_page_count_unreadable: {error}"
                        if marker not in errors:
                            errors.append(marker)
                        if record["parse_status"] == "success":
                            record["parse_status"] = "partial"
                    else:
                        record["pages"] = {"first": None, "last": None, "count": count}
                        record["errors"] = [e for e in errors if e != "missing: pages"]
                        if record["parse_status"] == "partial" and not record["errors"]:
                            record["parse_status"] = "success"
                        filled += 1
                    output.write(json.dumps(record, ensure_ascii=False) + "\n")
        os.replace(temp_path, jsonl)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
    return {"records": records, "pages_filled": filled, "unreadable": unreadable}


def main() -> None:
    """Parse CLI arguments, update the JSONL, and print a short result."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jsonl", type=Path, required=True)
    parser.add_argument("--pdf-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be at least 1")
    print(json.dumps(fill_pages(args.jsonl, args.pdf_dir, args.workers)))


if __name__ == "__main__":
    main()
