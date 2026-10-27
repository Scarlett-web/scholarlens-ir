"""Input correctness checks, including the unmerged parser's optional diagnostics."""

import json

import pytest

from backend.import_jsonl import load_jsonl


def write_records(tmp_path, records, bom=False):
    path = tmp_path / "input.jsonl"
    path.write_text(
        "\n".join(json.dumps(r) for r in records), encoding="utf-8-sig" if bom else "utf-8"
    )
    return path


def test_missing_fields_partial_and_body_quarantine(tmp_path):
    path = write_records(
        tmp_path,
        [
            {"paper_id": "mock-a", "parse_status": "partial", "year": 2024},
            {"paper_id": "mock-b", "fulltext": "broken \ufffd text", "errors": []},
            {"paper_id": "mock-c", "parse_status": "error"},
        ],
        bom=True,
    )
    original = path.read_bytes()
    records, meta = load_jsonl(path, "mock")
    assert len(records) == 2
    assert "date" not in records[0] and records[0]["affiliation"] == []
    assert records[1]["fulltext"] == ""
    assert meta["parser"] == {"success": 0, "partial": 1, "failed": 1, "unknown": 1}
    assert len(meta["skipped"]) == len(meta["body_quarantined"]) == 1
    assert path.read_bytes() == original


@pytest.mark.parametrize(
    "records,status",
    [
        ([{"paper_id": "mock-a"}, {"paper_id": "mock-a"}], "mock"),
        ([{"paper_id": "mock-a", "authors": "wrong"}], "mock"),
        ([{"paper_id": "mock-a", "date": "2024-02-30"}], "mock"),
        ([{"paper_id": "mock-a", "date": "2024-02"}], "mock"),
        ([{"paper_id": "mock-a", "date": "2024-01-01", "year": 2023}], "mock"),
        ([{"paper_id": "mock-a", "year": True}], "mock"),
        ([{"paper_id": "mock-a", "affiliations": []}], "mock"),
        ([{"paper_id": "mock-a"}], "real"),
        ([{"paper_id": "source-sha256:example"}], "mock"),
    ],
)
def test_reject_invalid_input_before_indexing(tmp_path, records, status):
    with pytest.raises(ValueError):
        load_jsonl(write_records(tmp_path, records), status)


def test_real_records_use_same_loader(tmp_path):
    records, meta = load_jsonl(
        write_records(
            tmp_path, [{"paper_id": "source-sha256:example", "date": "", "parse_status": "partial"}]
        ),
        "real",
    )
    assert records[0]["parse_status"] == "partial"
    assert meta["data_status"] == "real"


@pytest.mark.parametrize(
    "pages",
    [
        None,
        {"first": None, "last": None, "count": 12},
        {"first": None, "last": None, "count": None},
    ],
)
def test_pr2_fields_and_nulls_are_compatible(tmp_path, pages):
    # Explicit Mock structural fixture, not a delivered real paper.
    record = {
        "paper_id": "mock-pr2",
        "title": "",
        "authors": [],
        "date": "",
        "year": None,
        "affiliation": [],
        "address": [],
        "pages": pages,
        "abstract": "",
        "fulltext": "",
        "source_file": "paper.pdf",
        "pdf_path": "../oriPDFs.rar/oriPDFs/paper.pdf",
        "parse_status": "partial",
        "errors": ["missing: date"],
    }
    docs, meta = load_jsonl(write_records(tmp_path, [record]), "mock")
    assert docs[0]["pages"] == pages and docs[0]["source_file"] == "paper.pdf"
    assert meta["parser"]["partial"] == 1


@pytest.mark.parametrize(
    "field", ["authors", "affiliation", "address", "errors", "date", "pdf_path", "source_file"]
)
def test_null_in_nonnullable_fields_is_rejected(tmp_path, field):
    with pytest.raises(ValueError):
        load_jsonl(
            write_records(tmp_path, [{"paper_id": "mock-invalid-null", field: None}]), "mock"
        )
