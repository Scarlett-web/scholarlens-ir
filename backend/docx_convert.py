"""Bounded PDF-to-DOCX conversion for controlled local PDFs."""

from pathlib import Path
import time
import uuid
import subprocess
import sys
import os
import shutil
import hashlib

from docx import Document
from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import FileResponse
from pypdf import PdfReader

from backend.accounts import problem

MAX_INPUT = 20 * 1024 * 1024
MAX_PAGES = 300
MAX_TEXT = 5_000_000


def convert_local(pdf: Path, output: Path):
    """Extract text into a real reopenable DOCX; source PDF is never modified."""
    if not pdf.is_file() or pdf.stat().st_size > MAX_INPUT:
        raise problem(413, "file_too_large", "PDF不存在或超过20MiB")
    started = time.monotonic()
    try:
        reader = PdfReader(str(pdf), strict=True)
        if reader.is_encrypted or not 1 <= len(reader.pages) <= MAX_PAGES:
            raise problem(400, "invalid_file", "PDF需未加密且页数在1至300之间")
        document = Document()
        document.core_properties.title = "Converted paper"
        total = 0
        for number, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            total += len(text)
            if total > MAX_TEXT:
                raise problem(413, "file_too_large", "提取文本超过5MiB")
            if number > 1:
                document.add_page_break()
            document.add_heading(f"Page {number}", level=2)
            for paragraph in text.splitlines() or [""]:
                clean = "".join(c for c in paragraph if ord(c) >= 32 or c in "\t\n\r")
                document.add_paragraph(clean)
            if time.monotonic() - started > 30:
                raise problem(504, "conversion_timeout", "PDF转换超时")
        if total == 0:
            raise problem(422, "ocr_required", "PDF没有可提取文本，需要单独配置OCR")
        document.save(output)
        # Reopen immediately so callers never receive a corrupt package.
        Document(str(output))
        return output
    except (OSError, ValueError) as exc:
        if isinstance(exc, Exception) and getattr(exc, "status_code", None):
            raise
        raise problem(400, "conversion_failed", "PDF无法转换为DOCX") from exc


def cleanup_job(path: Path):
    """Delete only this conversion's generated temporary directory."""
    if path.name.startswith("job-") and len(path.name) == 36 and path.parent.name == "docx":
        shutil.rmtree(path, ignore_errors=True)


def convert_pdf_to_docx(pdf: Path, output_dir: Path, timeout: float = 30) -> Path:
    """Process boundary enforces wall-clock timeout even if a PDF parser is stuck."""
    output_dir.mkdir(parents=True, exist_ok=True)
    # Expired result directories can remain if a client/process disconnected before cleanup.
    for old in output_dir.glob("job-*"):
        if old.is_dir() and time.time() - old.stat().st_mtime > 3600:
            cleanup_job(old)
    job = output_dir / ("job-" + uuid.uuid4().hex)
    job.mkdir()
    output = job / "paper.docx"
    command = [
        sys.executable,
        "-m",
        "backend.docx_worker",
        str(pdf.resolve()),
        str(output.resolve()),
    ]
    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        stdout, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
        else:
            proc.kill()
        proc.communicate()
        cleanup_job(job)
        raise problem(504, "conversion_timeout", "PDF转换超过时间限制") from exc
    if proc.returncode:
        cleanup_job(job)
        if stdout.strip() == b"ocr_required":
            raise problem(422, "ocr_required", "PDF没有可提取文本，需要OCR")
        raise problem(400, "conversion_failed", "PDF无法转换为DOCX")
    try:
        Document(output)
    except Exception as exc:
        cleanup_job(job)
        raise problem(500, "conversion_failed", "转换结果校验失败") from exc
    return output


def router(settings, store, read_paper, resolve_document_pdf, get_upload):
    api = APIRouter(prefix="/api")
    output_dir = store.root / "docx"

    def deliver(pdf: Path, name: str, tasks: BackgroundTasks):
        output = convert_pdf_to_docx(pdf, output_dir)
        tasks.add_task(cleanup_job, output.parent)
        return FileResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=f"{Path(name).stem or 'paper'}.docx",
            content_disposition_type="attachment",
            headers={"X-ScholarLens-Conversion": "text-only", "Cache-Control": "private, no-store"},
        )

    @api.get("/papers/{paper_id:path}/docx")
    def paper_docx(paper_id: str, tasks: BackgroundTasks):
        doc, _ = read_paper(paper_id)
        pdf = resolve_document_pdf(doc)
        if pdf is None:
            raise problem(404, "pdf_not_available", "原始PDF尚未交付或暂不可访问")
        return deliver(pdf, doc.get("source_file", "paper"), tasks)

    @api.get("/uploads/{upload_id}/docx")
    def upload_docx(upload_id: str, tasks: BackgroundTasks, user=Depends(store.current)):
        row = get_upload(upload_id, user)
        pdf = store.root / "uploads" / "files" / row["stored_name"]
        if not pdf.is_file():
            raise problem(404, "pdf_not_available", "上传PDF不存在")
        if (
            not pdf.resolve().is_relative_to((store.root / "uploads/files").resolve())
            or hashlib.sha256(pdf.read_bytes()).hexdigest() != row["sha256"]
        ):
            raise problem(409, "source_integrity_error", "上传文件校验未通过")
        return deliver(pdf, row["original_name"], tasks)

    return api
