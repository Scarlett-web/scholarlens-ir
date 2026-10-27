"""Quarantined PDF uploads, explicit review, recoverable parsing and separate indexing."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time
from typing import Literal
import uuid
from xml.etree import ElementTree as ET

from elasticsearch.helpers import scan
from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, UploadFile
from backend.pdf_response import PDFResponse
import httpx
from pydantic import BaseModel, ConfigDict, Field
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from backend.accounts import now, problem
from backend.import_jsonl import load_jsonl, import_records
from backend.schema import Paper
from backend.api_models import Page
from backend.upload_vector import vectorize_uploads

MAX_BYTES = 20 * 1024 * 1024
MAX_PAGES = 300
NS = {"t": "http://www.tei-c.org/ns/1.0"}


def call_grobid(settings, path: Path) -> bytes:
    """Bounded call to an operator-configured service; injection point for controlled tests."""
    with path.open("rb") as pdf, httpx.Client(timeout=120, trust_env=False) as client:
        with client.stream(
            "POST",
            settings.grobid_url.rstrip("/") + "/api/processFulltextDocument",
            files={"input": ("paper.pdf", pdf, "application/pdf")},
        ) as response:
            response.raise_for_status()
            data = bytearray()
            for block in response.iter_bytes():
                data.extend(block)
                if len(data) > MAX_BYTES:
                    raise ValueError("TEI too large")
    return bytes(data)


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject"]
    reason: str = Field(default="", max_length=1000)


class UploadResponse(BaseModel):
    id: str
    original_name: str
    sha256: str
    size: int
    status: str
    reason: str
    created_at: str
    updated_at: str
    paper_id: str | None
    attempts: int
    archived: bool = False


def public(row):
    return {key: row[key] for key in UploadResponse.model_fields}


def verify_pdf(path: Path):
    """Parse a bounded PDF rather than trusting an extension or signature alone."""
    if not path.stat().st_size <= MAX_BYTES:
        raise problem(413, "file_too_large", "PDF最大20MiB")
    with path.open("rb") as f:
        if f.read(5) != b"%PDF-":
            raise problem(400, "invalid_file", "文件不是PDF")
        try:
            reader = PdfReader(f, strict=True)
            if reader.is_encrypted or not 1 <= len(reader.pages) <= MAX_PAGES:
                raise problem(400, "invalid_file", "PDF需未加密且页数在1至300之间")
        except (ValueError, OSError, PyPdfError) as exc:
            raise problem(400, "invalid_file", "PDF结构无效") from exc


def tei_to_paper(xml: bytes, sha: str, original: str, relative_pdf: str, page_count: int) -> dict:
    """Parse this upload only. Existing parser code and all formal IDs are untouched."""
    if len(xml) > MAX_BYTES or b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
        raise ValueError("invalid TEI")
    root = ET.fromstring(xml)
    if root.tag != "{http://www.tei-c.org/ns/1.0}TEI":
        raise ValueError("not TEI")

    blocks = {
        "p",
        "head",
        "div",
        "list",
        "item",
        "formula",
        "ab",
        "table",
        "row",
        "cell",
        "figure",
        "figDesc",
        "note",
    }

    def raw_text(node):
        parts = [node.text or ""]
        for child in node:
            block = child.tag.rsplit("}", 1)[-1] in blocks
            if block:
                parts.append("\n")
            parts.append(raw_text(child))
            if block:
                parts.append("\n")
            parts.append(child.tail or "")
        return "".join(parts)

    def text(node):
        return "" if node is None else " ".join(raw_text(node).split())

    def unique(nodes):
        return list(dict.fromkeys(text(n) for n in nodes if text(n)))

    title = text(root.find(".//t:teiHeader//t:sourceDesc//t:analytic/t:title", NS))
    if not title:
        title = text(root.find(".//t:teiHeader/t:fileDesc/t:titleStmt/t:title", NS))
    authors = unique(
        root.findall(".//t:teiHeader//t:sourceDesc//t:analytic/t:author/t:persName", NS)
    )
    # Inline name parts often have no tail whitespace in TEI.
    authors = (
        list(
            dict.fromkeys(
                " ".join(text(part) for part in name if text(part))
                for name in root.findall(
                    ".//t:teiHeader//t:sourceDesc//t:analytic/t:author/t:persName", NS
                )
            )
        )
        or authors
    )
    authors = list(dict.fromkeys(a for a in authors if a))
    date = ""
    year = None
    date_nodes = root.findall(".//t:teiHeader//t:publicationStmt/t:date", NS) + root.findall(
        ".//t:teiHeader//t:biblStruct//t:imprint/t:date", NS
    )
    for node in date_nodes:
        value = node.get("when") or text(node)
        if re.fullmatch(r"\d{4}(?:-\d{2})?(?:-\d{2})?", value):
            year = int(value[:4]) or None
            if len(value) == 10:
                try:
                    datetime.strptime(value, "%Y-%m-%d")
                    date = value
                except ValueError:
                    pass
            break
    affiliations = unique(root.findall(".//t:teiHeader//t:affiliation/t:orgName", NS))
    addresses = []
    for node in root.findall(".//t:teiHeader//t:affiliation/t:address", NS):
        addresses.append(
            " ".join(text(part) for part in node if text(part)) if list(node) else text(node)
        )
    abstract = text(root.find(".//t:teiHeader//t:abstract", NS))
    body = root.find("./t:text/t:body", NS)
    fulltext = "" if body is None else "\n".join(text(node) for node in body if text(node))
    if not any((title, abstract, fulltext)):
        raise ValueError("TEI contains no indexable text")
    errors = [
        f"missing:{key}"
        for key, value in [
            ("title", title),
            ("authors", authors),
            ("date", date),
            ("affiliation", affiliations),
            ("address", addresses),
            ("abstract", abstract),
            ("fulltext", fulltext),
        ]
        if not value
    ]
    if "\ufffd" in fulltext:
        errors.append("unreadable_characters_in_fulltext")
    return Paper(
        paper_id="upload-sha256:" + sha,
        title=title,
        authors=authors,
        date=date,
        year=year,
        affiliation=affiliations,
        address=list(dict.fromkeys(a for a in addresses if a)),
        abstract=abstract,
        fulltext=fulltext,
        pages={"count": page_count},
        pdf_path=relative_pdf,
        source_file=original,
        parse_status="partial" if errors else "success",
        errors=errors,
    ).model_dump()


def router(es, settings, store):
    if (
        not settings.uploads_index.startswith("scholarlens-uploads-")
        or settings.uploads_index == settings.index
    ):
        raise ValueError("uploads require a separate scholarlens-uploads-* alias")
    api = APIRouter(prefix="/api")
    storage = store.root / "uploads" / "files"
    storage.mkdir(parents=True, exist_ok=True)

    def admin(user=Depends(store.current)):
        if user["role"] != "admin":
            raise problem(403, "forbidden", "需要管理员权限")
        return user

    def get_upload(upload_id, user):
        with store.connect() as db:
            row = db.execute("SELECT * FROM uploads WHERE id=?", (upload_id,)).fetchone()
        if row is None or (row["user_id"] != user["id"] and user["role"] != "admin"):
            raise problem(404, "not_found", "上传记录不存在")
        return row

    @api.post("/uploads", response_model=UploadResponse, status_code=201)
    def upload(file: UploadFile = File(...), user=Depends(store.current)):
        name = Path((file.filename or "").replace("\\", "/")).name
        if not name.lower().endswith(".pdf") or len(name) > 200 or any(ord(c) < 32 for c in name):
            raise problem(400, "invalid_file", "只接收PDF文件名")
        upload_id = uuid.uuid4().hex
        path = storage / (upload_id + ".pdf")
        size = 0
        digest = hashlib.sha256()
        try:
            with store.connect() as db:
                pending = db.execute(
                    "SELECT count(*) FROM uploads WHERE user_id=? AND status IN ('pending','approved','processing')",
                    (user["id"],),
                ).fetchone()[0]
                if pending >= 20:
                    raise problem(429, "rate_limited", "未处理上传数量已达20")
            with path.open("xb") as out:
                while True:
                    block = file.file.read(65536)
                    if not block:
                        break
                    size += len(block)
                    if size > MAX_BYTES:
                        raise problem(413, "file_too_large", "PDF最大20MiB")
                    digest.update(block)
                    out.write(block)
            verify_pdf(path)
            with store.connect() as db:
                stamp = now()
                db.execute(
                    "INSERT INTO uploads(id,user_id,original_name,stored_name,sha256,size,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        upload_id,
                        user["id"],
                        name,
                        path.name,
                        digest.hexdigest(),
                        size,
                        "pending",
                        stamp,
                        stamp,
                    ),
                )
                row = db.execute("SELECT * FROM uploads WHERE id=?", (upload_id,)).fetchone()
            return public(row)
        except Exception as e:
            path.unlink(missing_ok=True)  # Only this request's newly created isolated file.
            if isinstance(e, sqlite3.IntegrityError):
                raise problem(409, "duplicate_record", "该PDF已上传") from e
            raise
        finally:
            file.file.close()

    @api.get("/uploads", response_model=Page[UploadResponse])
    def uploads(
        page: int = Query(default=1, ge=1, le=10000),
        page_size: int = Query(default=20, ge=1, le=100),
        user=Depends(store.current),
    ):
        with store.connect() as db:
            total = db.execute(
                "SELECT count(*) FROM uploads WHERE user_id=? AND archived=0", (user["id"],)
            ).fetchone()[0]
            rows = db.execute(
                "SELECT * FROM uploads WHERE user_id=? AND archived=0 ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (user["id"], page_size, (page - 1) * page_size),
            ).fetchall()
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "results": [public(r) for r in rows],
        }

    @api.get("/uploads/{upload_id}", response_model=UploadResponse)
    def upload_status(upload_id: str, user=Depends(store.current)):
        return public(get_upload(upload_id, user))

    @api.get("/me/uploads")
    def my_uploads(
        page: int = Query(default=1, ge=1, le=10000),
        page_size: int = Query(default=20, ge=1, le=100),
        user=Depends(store.current),
    ):
        return uploads(page, page_size, user)

    @api.get("/me/papers")
    def my_papers(
        page: int = Query(default=1, ge=1, le=10000),
        page_size: int = Query(default=20, ge=1, le=100),
        user=Depends(store.current),
    ):
        listing = uploads(page, page_size, user)
        results = []
        for row in listing["results"]:
            item = {
                **row,
                "paper_available": row["status"] == "indexed",
                "review_status": row["status"],
            }
            results.append(item)
        return {**listing, "results": results}

    @api.get("/uploads/{upload_id}/result", response_model=UploadResponse)
    def upload_result(upload_id: str, user=Depends(store.current)):
        return public(get_upload(upload_id, user))

    @api.get("/admin/uploads", response_model=Page[UploadResponse])
    def admin_uploads(
        page: int = Query(default=1, ge=1, le=10000),
        page_size: int = Query(default=20, ge=1, le=100),
        user=Depends(admin),
    ):
        with store.connect() as db:
            total = db.execute("SELECT count(*) FROM uploads WHERE archived=0").fetchone()[0]
            rows = db.execute(
                "SELECT * FROM uploads WHERE archived=0 ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (page_size, (page - 1) * page_size),
            ).fetchall()
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "results": [public(r) for r in rows],
        }

    @api.post("/admin/uploads/{upload_id}/review", response_model=UploadResponse)
    def review(upload_id: str, body: Review, user=Depends(admin)):
        current = get_upload(upload_id, user)
        if current["archived"]:
            raise problem(409, "invalid_state", "记录已归档")
        status = "approved" if body.decision == "approve" else "rejected"
        with store.connect() as db:
            changed = db.execute(
                "UPDATE uploads SET status=?,reason=?,updated_at=? WHERE id=? AND status='pending'",
                (status, body.reason, now(), upload_id),
            )
            if not changed.rowcount:
                raise problem(409, "invalid_state", "只能审核待审核记录")
            db.execute(
                "INSERT INTO reviews(upload_id,admin_id,decision,reason,created_at) VALUES(?,?,?,?,?)",
                (upload_id, user["id"], body.decision, body.reason, now()),
            )
            owner = db.execute("SELECT user_id FROM uploads WHERE id=?", (upload_id,)).fetchone()[0]
            db.execute(
                "INSERT INTO notifications(user_id,kind,message,created_at) VALUES(?,?,?,?)",
                (owner, "upload_review", f"上传论文审核结果：{status}", now()),
            )
            row = db.execute("SELECT * FROM uploads WHERE id=?", (upload_id,)).fetchone()
        return public(row)

    @api.get("/admin/uploads/{upload_id}/pdf")
    def admin_preview(upload_id: str, user=Depends(admin)):
        row = get_upload(upload_id, user)
        path = storage / row["stored_name"]
        if not path.is_file():
            raise problem(404, "pdf_not_available", "上传文件已不存在")
        verify_pdf(path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise problem(409, "source_integrity_error", "上传文件校验未通过")
        return PDFResponse(
            path,
            media_type="application/pdf",
            filename="review.pdf",
            content_disposition_type="inline",
            headers={
                "X-ScholarLens-Upload-Status": row["status"],
                "X-Content-Type-Options": "nosniff",
            },
        )

    @api.post("/admin/uploads", response_model=UploadResponse, status_code=201)
    def admin_upload(file: UploadFile = File(...), user=Depends(admin)):
        item = upload(file, user)
        return review(item["id"], Review(decision="approve", reason="admin_upload"), user)

    def process_job(upload_id):
        # The transaction reserves one upload; a database lease serializes publication.
        lease = uuid.uuid4().hex
        with store.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS leases(name TEXT PRIMARY KEY,owner TEXT,expires REAL)"
            )
            db.execute(
                "INSERT INTO leases VALUES('upload-index',?,?) ON CONFLICT(name) DO UPDATE SET owner=excluded.owner,expires=excluded.expires WHERE leases.expires<?",
                (lease, time.time() + 600, time.time()),
            )
            owned = (
                db.execute("SELECT owner FROM leases WHERE name='upload-index'").fetchone()[0]
                == lease
            )
            if not owned:
                db.execute(
                    "UPDATE uploads SET status='failed',reason='index_busy_retry',updated_at=? WHERE id=?",
                    (now(), upload_id),
                )
                return
        try:
            with store.connect() as db:
                row = db.execute("SELECT * FROM uploads WHERE id=?", (upload_id,)).fetchone()
            path = storage / row["stored_name"]
            verify_pdf(path)
            if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
                raise ValueError("upload hash mismatch")
            data = call_grobid(settings, path)
            paper = tei_to_paper(
                data,
                row["sha256"],
                row["original_name"],
                "uploads/files/" + row["stored_name"],
                len(PdfReader(path).pages),
            )
            parsed = (
                store.root / "uploads" / (upload_id + "-parsed-" + uuid.uuid4().hex[:8] + ".jsonl")
            )
            parsed.write_text(json.dumps(paper, ensure_ascii=False) + "\n", encoding="utf-8")
            docs = (
                {h["_id"]: h["_source"] for h in scan(es, index=settings.uploads_index)}
                if es.indices.exists_alias(name=settings.uploads_index)
                else {}
            )
            # Reuse the validated importer and keep all prior upload generations.
            paper = Paper.model_validate(paper).model_dump()
            for d in docs.values():
                d.pop("date_value", None)
                if d.get("parse_status") == "unknown":
                    d["parse_status"] = None
            docs[paper["paper_id"]] = paper
            source = store.root / "uploads" / ("index-input-" + uuid.uuid4().hex + ".jsonl")
            source.write_text(
                "".join(json.dumps(d, ensure_ascii=False) + "\n" for d in docs.values()),
                encoding="utf-8",
            )
            records, meta = load_jsonl(source, "real")
            report = import_records(es, settings.uploads_index, records, meta)
            try:
                vector_report = vectorize_uploads(settings)
            except Exception as exc:
                # The approved keyword generation remains valid. Report vector retry separately.
                vector_report = {
                    "status": "dependency_unavailable",
                    "error_type": type(exc).__name__,
                }
            (store.root / "uploads" / ("import-" + uuid.uuid4().hex + ".json")).write_text(
                json.dumps({"keyword": report, "vector": vector_report}, indent=2), encoding="utf-8"
            )
            with store.connect() as db:
                db.execute(
                    "UPDATE uploads SET status='indexed',reason='',paper_id=?,generation=?,updated_at=? WHERE id=?",
                    (paper["paper_id"], report["generation"], now(), upload_id),
                )
                db.execute(
                    "INSERT INTO notifications(user_id,kind,message,created_at) VALUES(?,?,?,?)",
                    (
                        row["user_id"],
                        "upload_indexed",
                        "论文关键词索引已完成；向量状态见任务/能力接口",
                        now(),
                    ),
                )
        except Exception as e:
            reason = (
                "parse_dependency_unavailable"
                if isinstance(e, (httpx.HTTPError, ConnectionError))
                else "processing_failed"
            )
            with store.connect() as db:
                db.execute(
                    "UPDATE uploads SET status='failed',reason=?,updated_at=? WHERE id=?",
                    (reason, now(), upload_id),
                )
        finally:
            with store.connect() as db:
                db.execute("DELETE FROM leases WHERE name='upload-index' AND owner=?", (lease,))

    @api.post("/admin/uploads/{upload_id}/process", status_code=202, response_model=UploadResponse)
    def process(upload_id: str, tasks: BackgroundTasks, user=Depends(admin)):
        row = get_upload(upload_id, user)
        if row["archived"]:
            raise problem(409, "invalid_state", "归档记录不再处理")
        if row["status"] not in ("approved", "failed", "dependency_unavailable", "processing"):
            raise problem(409, "invalid_state", "只有审核通过的任务可以解析")
        if (
            row["status"] == "processing"
            and (
                datetime.now(timezone.utc) - datetime.fromisoformat(row["updated_at"])
            ).total_seconds()
            < 600
        ):
            raise problem(409, "invalid_state", "解析正在进行")
        if not settings.grobid_url:
            with store.connect() as db:
                db.execute(
                    "UPDATE uploads SET status='dependency_unavailable',reason='grobid_not_configured',updated_at=? WHERE id=?",
                    (now(), upload_id),
                )
            raise problem(
                503, "dependency_unavailable", "GROBID尚未配置；上传原件已保留，可配置后重试"
            )
        with store.connect() as db:
            changed = db.execute(
                "UPDATE uploads SET status='processing',reason='',attempts=attempts+1,updated_at=? WHERE id=? AND status=? AND updated_at=?",
                (now(), upload_id, row["status"], row["updated_at"]),
            )
            if not changed.rowcount:
                raise problem(409, "invalid_state", "任务状态已改变，请刷新后重试")
            row = db.execute("SELECT * FROM uploads WHERE id=?", (upload_id,)).fetchone()
        tasks.add_task(process_job, upload_id)
        return public(row)

    @api.post("/admin/uploads/vectorize")
    def retry_vectors(user=Depends(admin)):
        try:
            return vectorize_uploads(settings)
        except Exception as exc:
            raise problem(503, "dependency_unavailable", "上传向量构建失败，旧索引已保留") from exc

    @api.delete("/admin/uploads/{upload_id}")
    def archive_upload(upload_id: str, user=Depends(admin)):
        row = get_upload(upload_id, user)
        if row["status"] == "processing":
            raise problem(409, "invalid_state", "处理中的任务请稍后归档")
        with store.connect() as db:
            db.execute("UPDATE uploads SET archived=1,updated_at=? WHERE id=?", (now(), upload_id))
            db.execute(
                "INSERT INTO reviews(upload_id,admin_id,decision,reason,created_at) VALUES(?,?,?,?,?)",
                (
                    upload_id,
                    user["id"],
                    "archive",
                    "removed from review queue; source retained",
                    now(),
                ),
            )
        return {"archived": True, "source_preserved": True, "indexed_document_preserved": True}

    return api
