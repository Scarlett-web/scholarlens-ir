"""Convert a directory of GROBID TEI files to traceable JSONL records."""

from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

NS = {"t": "http://www.tei-c.org/ns/1.0"}
SPACE = re.compile(r"\s+")
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def clean(value: str) -> str:
    """Collapse excess whitespace in one field."""
    return SPACE.sub(" ", value).strip()


def content(element: ET.Element | None) -> str:
    """Return normalized text from a TEI element, or an empty string."""
    return clean("".join(element.itertext())) if element is not None else ""


def unique(values: list[str]) -> list[str]:
    """Keep nonempty values in their original order without duplicates."""
    return list(dict.fromkeys(value for value in values if value))


def digest(path: Path) -> str:
    """Return the SHA-256 of a source file."""
    h = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def convert(xml_path: Path, pdf_dir: Path, source_map: dict[str, str] | None = None) -> dict:
    """Convert one XML; report malformed input or missing fields in errors."""
    stem = xml_path.name.removesuffix(".grobid.tei.xml").removesuffix(".tei.xml").removesuffix(".xml")
    source_file = (source_map or {}).get(xml_path.name, f"{stem}.pdf")
    pdf_path = pdf_dir / source_file
    errors: list[str] = []
    source = pdf_path if pdf_path.is_file() else xml_path
    if source == xml_path:
        errors.append("source_pdf_missing: paper_id uses XML hash")
    record = {
        "paper_id": "source-sha256:" + hashlib.sha256((source_file + "\0" + digest(source)).encode("utf-8")).hexdigest(),
        "source_file": source_file if pdf_path.is_file() else "",
        "title": "", "authors": [], "date": "", "year": None,
        "affiliation": [], "address": [], "pages": None,
        "abstract": "", "fulltext": "",
        "pdf_path": Path(os.path.relpath(pdf_path.resolve(), PROJECT_ROOT)).as_posix()
        if pdf_path.is_file() else "",
        "parse_status": "error", "errors": errors,
    }
    try:
        root = ET.parse(xml_path).getroot()
        if root.tag != "{http://www.tei-c.org/ns/1.0}TEI":
            raise ValueError("root element is not TEI")
    except (ET.ParseError, ValueError, OSError) as exc:
        errors.append(f"invalid_xml: {exc}")
        return record

    header = root.find("t:teiHeader", NS)
    if header is None:
        errors.append("missing: teiHeader")
    else:
        record["title"] = content(header.find("t:fileDesc/t:titleStmt/t:title", NS))
        analytic = header.find("t:fileDesc/t:sourceDesc/t:biblStruct/t:analytic", NS)
        if analytic is not None:
            for author in analytic.findall("t:author", NS):
                person = author.find("t:persName", NS)
                if person is not None:
                    forenames = [content(x) for x in person.findall("t:forename", NS)]
                    surname = content(person.find("t:surname", NS))
                    name = clean(" ".join([*forenames, surname]))
                else:
                    name = content(author.find("t:orgName", NS))
                if name:
                    record["authors"].append(name)
                for affiliation in author.findall("t:affiliation", NS):
                    orgs = [content(x) for x in affiliation.findall("t:orgName", NS)]
                    record["affiliation"].extend(orgs)
                    for address in affiliation.findall("t:address", NS):
                        record["address"].append(content(address))
        record["affiliation"] = unique(record["affiliation"])
        record["address"] = unique(record["address"])
        imprint = header.find("t:fileDesc/t:sourceDesc/t:biblStruct/t:monogr/t:imprint", NS)
        if imprint is not None:
            date = imprint.find("t:date[@type='published']", NS)
            when = date.get("when", "") if date is not None else ""
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", when):
                try:
                    dt.date.fromisoformat(when)
                except ValueError:
                    errors.append(f"invalid_date: {when}")
                else:
                    record["date"] = when
                    record["year"] = int(when[:4])
            elif re.fullmatch(r"\d{4}", when):
                record["year"] = int(when)
            page = imprint.find("t:biblScope[@unit='page']", NS)
            if page is not None:
                first, last = page.get("from"), page.get("to")
                if first and last and first.isdigit() and last.isdigit() and int(last) >= int(first):
                    record["pages"] = {"first": int(first), "last": int(last), "count": int(last) - int(first) + 1}
        record["abstract"] = content(header.find("t:profileDesc/t:abstract", NS))

    body = root.find("t:text/t:body", NS)
    if body is not None:
        paragraphs = [content(p) for p in body.findall(".//t:p", NS)]
        record["fulltext"] = "\n\n".join(p for p in paragraphs if p)
    for field in ("title", "authors", "date", "affiliation", "address", "pages", "fulltext"):
        if not record[field]:
            errors.append(f"missing: {field}")
    record["parse_status"] = "partial" if errors else "success"
    return record


def main() -> None:
    """Write one JSON object per XML and continue after individual failures."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xml-dir", type=Path, required=True)
    parser.add_argument("--pdf-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-map", type=Path, help="JSON object mapping XML filenames to PDF filenames")
    parser.add_argument("--report", type=Path, help="Write JSON quality report")
    args = parser.parse_args()
    started = time.perf_counter()
    source_map = json.loads(args.source_map.read_text(encoding="utf-8")) if args.source_map else {}
    files = sorted([*args.xml_dir.glob("*.xml")])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = ("source_file", "title", "authors", "date", "year", "affiliation", "address", "pages", "abstract", "fulltext", "pdf_path")
    counts = {field: 0 for field in fields}
    statuses = {"success": 0, "partial": 0, "error": 0}
    failures = []
    seen: dict[str, str] = {}
    duplicates = []
    issue_counts: Counter[str] = Counter()
    with args.output.open("w", encoding="utf-8", newline="\n") as output:
        for path in files:
            record = convert(path, args.pdf_dir, source_map)
            if record["paper_id"] in seen:
                record["errors"].append(f"duplicate_paper_id: {seen[record['paper_id']]}")
                record["parse_status"] = "partial" if record["parse_status"] != "error" else "error"
                duplicates.append({"file": path.name, "same_as": seen[record["paper_id"]]})
            else:
                seen[record["paper_id"]] = path.name
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
            statuses[record["parse_status"]] += 1
            issue_counts.update(record["errors"])
            for field in fields:
                counts[field] += bool(record[field])
            if record["parse_status"] == "error" or any(not error.startswith("missing:") for error in record["errors"]):
                failures.append({"file": path.name, "status": record["parse_status"], "errors": record["errors"]})
    report = {
        "input_xml_count": len(files), "output_count": sum(statuses.values()),
        "status_counts": statuses,
        "parse_success_rate": round((statuses["success"] + statuses["partial"]) / len(files), 4) if files else 0,
        "complete_record_rate": round(statuses["success"] / len(files), 4) if files else 0,
        "field_completeness": {field: {"nonempty": count, "rate": round(count / len(files), 4) if files else 0} for field, count in counts.items()},
        "duplicate_paper_id_count": len(duplicates), "duplicates": duplicates,
        "issue_counts": dict(issue_counts),
        "failure_count": len(failures), "failure_list": failures,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("input_xml_count", "output_count", "status_counts", "parse_success_rate", "duplicate_paper_id_count", "failure_count", "elapsed_seconds")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
