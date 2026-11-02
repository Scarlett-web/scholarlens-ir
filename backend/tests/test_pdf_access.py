"""Path boundary checks without creating or pretending to deliver any PDF."""

from pathlib import Path

import pytest

from backend.config import Settings
from backend.pdf_access1 import resolve_pdf


def test_pdf_access_disabled_by_default():
    assert resolve_pdf("data/sample/mock-0001.pdf", Settings()) is None


@pytest.mark.parametrize(
    "stored",
    [
        "",
        "missing.pdf",
        "../outside.pdf",
        "C:/private/paper.pdf",
        "https://example.invalid/paper.pdf",
        "//host/share/paper.pdf",
        "\\\\host\\share\\paper.pdf",
        "/etc/passwd",
        "bad\x00name.pdf",
    ],
)
def test_missing_and_disallowed_paths(tmp_path, stored):
    settings = Settings(pdf_root=str(tmp_path), pdf_path_base=str(tmp_path))
    assert resolve_pdf(stored, settings) is None


def test_existing_non_pdf_is_not_served(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("ordinary text; not a PDF", encoding="utf-8")
    assert (
        resolve_pdf(path.name, Settings(pdf_root=str(tmp_path), pdf_path_base=str(tmp_path)))
        is None
    )
    assert path.read_text(encoding="utf-8") == "ordinary text; not a PDF"


def test_pdf_config_reads_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("SCHOLARLENS_PDF_ROOT", str(tmp_path))
    monkeypatch.setenv("SCHOLARLENS_PDF_PATH_BASE", str(Path.cwd()))
    settings = Settings.from_env()
    assert settings.pdf_root == str(tmp_path) and settings.pdf_path_base == str(Path.cwd())


def test_batch_mapping_hash_and_boundaries(tmp_path):
    import csv
    import hashlib
    import json
    from dataclasses import replace
    from backend.pdf_access1 import resolve_document_pdf

    new_root = tmp_path / "new"
    new_root.mkdir()
    raw = b"%PDF-1.4\ncontrolled resolver fixture"
    (new_root / "paper.pdf").write_bytes(raw)
    roots = tmp_path / "roots.json"
    roots.write_text(json.dumps({"new": str(new_root), "old": None}))
    manifest = tmp_path / "manifest.csv"
    def write_row(batch="new", name="paper.pdf", digest=None):
        with manifest.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=["paper_id", "source_file", "source_batch", "pdf_sha256"])
            writer.writeheader()
            writer.writerow({"paper_id": "p", "source_file": name, "source_batch": batch, "pdf_sha256": digest or hashlib.sha256(raw).hexdigest()})
        from backend.pdf_access1 import _manifest
        _manifest.cache_clear()
    settings = replace(Settings(), pdf_manifest_path=str(manifest), pdf_roots_path=str(roots))
    doc = {"paper_id": "p", "source_file": "paper.pdf"}
    write_row()
    assert resolve_document_pdf(doc, settings) == new_root / "paper.pdf"
    write_row(batch="old")
    assert resolve_document_pdf(doc, settings) is None
    write_row(digest="0" * 64)
    assert resolve_document_pdf(doc, settings) is None
    write_row(name="../paper.pdf")
    assert resolve_document_pdf({**doc, "source_file": "../paper.pdf"}, settings) is None
