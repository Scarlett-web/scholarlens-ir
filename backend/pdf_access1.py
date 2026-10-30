"""Resolve only indexed PDFs inside an explicitly configured local directory."""

from pathlib import Path
import csv
import hashlib
import json
from dataclasses import replace
from functools import lru_cache

from backend.config import Settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def resolve_pdf(pdf_path: str, settings: Settings) -> Path | None:
    """Return a verified local path, or None for missing/disallowed/unreadable sources.

    No basename fallback, URI fetching, file creation or metadata rewriting occurs.
    Relative paths retain the parser's project-root semantics unless explicitly configured.
    """
    if not settings.pdf_root or not pdf_path or any(ord(c) < 32 for c in pdf_path):
        return None
    # Windows drive paths, UNC/absolute paths and URI schemes are not public PDF inputs.
    if ":" in pdf_path or pdf_path.startswith(("/", "\\")):
        return None
    try:
        root = Path(settings.pdf_root).resolve(strict=True)
        base = (
            Path(settings.pdf_path_base).resolve(strict=True)
            if settings.pdf_path_base
            else PROJECT_ROOT
        )
        relative = Path(pdf_path)
        if relative.is_absolute():
            return None
        candidate = (base / relative).resolve(strict=True)
        if not root.is_dir() or not candidate.is_relative_to(root):
            return None
        if candidate.suffix.lower() != ".pdf" or not candidate.is_file():
            return None
        with candidate.open("rb") as source:
            if source.read(5) != b"%PDF-":
                return None
        return candidate
    except (OSError, ValueError, RuntimeError):
        return None


@lru_cache(maxsize=8)
def _manifest(path: str, mtime: int, size: int):
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    result = {r["paper_id"]: r for r in rows}
    if len(rows) != len(result):
        raise ValueError("ambiguous PDF manifest")
    return result


@lru_cache(maxsize=256)
def _file_hash(path: str, mtime: int, size: int):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def resolve_document_pdf(doc: dict, settings: Settings) -> Path | None:
    """Use original path, or an explicitly provided ID/source/hash manifest for flat migration."""
    if not settings.pdf_manifest_path:
        return resolve_pdf(doc.get("pdf_path", ""), settings)
    if not settings.pdf_root and not settings.pdf_roots_path:
        return None
    try:
        manifest_path = Path(settings.pdf_manifest_path)
        stat = manifest_path.stat()
        row = _manifest(str(manifest_path), stat.st_mtime_ns, stat.st_size).get(doc["paper_id"])
        if not row or row["source_file"] != doc.get("source_file"):
            return None
        if settings.pdf_roots_path:
            roots = json.loads(Path(settings.pdf_roots_path).read_text(encoding="utf-8"))
            root = roots.get(row.get("source_batch", ""))
            if not isinstance(root, str) or not root:
                return None
            settings = replace(settings, pdf_root=root, pdf_path_base=root)
        name = row["source_file"]
        if not name or any(c in name for c in "/\\:") or name in (".", ".."):
            return None
        candidate = resolve_pdf(name, replace(settings, pdf_path_base=settings.pdf_root))
        if not candidate:
            return None
        stat = candidate.stat()
        if _file_hash(str(candidate), stat.st_mtime_ns, stat.st_size) != row["pdf_sha256"].lower():
            return None
        return candidate
    except (OSError, ValueError, KeyError, RuntimeError, TypeError, AttributeError):
        return None
