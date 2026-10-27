"""Path boundary checks without creating or pretending to deliver any PDF."""

from pathlib import Path

import pytest

from backend.config import Settings
from backend.pdf_access import resolve_pdf


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
