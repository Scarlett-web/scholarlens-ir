"""Report dependencies from current state without exposing server configuration."""

import json
from pathlib import Path
from dataclasses import replace
from elasticsearch.helpers import scan

from fastapi import APIRouter
from pydantic import BaseModel

from backend.retrieval import vector_metadata, upload_vector_indices
import os
from backend.retrieval import encoder
from backend.rag import provider_verified
from backend.pdf_access import resolve_document_pdf, resolve_pdf
import httpx


class Capability(BaseModel):
    status: str
    reason: str


class CapabilitiesResponse(BaseModel):
    modules: dict[str, Capability]
    data_status: str


def router(es, settings, metadata, store):
    api = APIRouter(prefix="/api")

    @api.get("/capabilities", response_model=CapabilitiesResponse)
    def capabilities():
        modules = {}
        try:
            base, meta = metadata()
            es.count(index=base)
            modules["keyword_search"] = {"status": "ready", "reason": "当前论文索引可访问"}
        except Exception:
            base = None
            meta = {"data_status": "unknown"}
            modules["keyword_search"] = {
                "status": "dependency_unavailable",
                "reason": "论文索引尚未就绪",
            }
        try:
            if not base:
                raise ValueError("no base")
            generation, vector_meta = vector_metadata(es, settings, base)
            upload_vector_indices(es, settings)
            if es.count(index=generation)["count"] != vector_meta["chunks"]:
                raise ValueError("incomplete vector index")
            encoder(settings.model_dir)
            vector = {"status": "ready", "reason": "独立真实向量索引与当前论文版本一致"}
        except Exception:
            vector = {"status": "dependency_unavailable", "reason": "向量索引或本地模型尚未就绪"}
        modules["semantic_search"] = vector
        modules["hybrid_search"] = (
            vector if modules["keyword_search"]["status"] == "ready" else modules["keyword_search"]
        )
        configured = bool(settings.ai_api_key and settings.ai_base_url and settings.ai_model)
        modules["ai_qa"] = {
            "status": "ready"
            if configured and provider_verified(settings) and vector["status"] == "ready"
            else "dependency_unavailable"
            if configured
            else "not_configured",
            "reason": "AI已配置；ready仅在近5分钟内实际生成及引用校验成功后返回，首次可直接尝试问答"
            if configured
            else "AI Key、地址或模型未配置",
        }
        preview_ready = False
        with store.connect() as db:
            uploaded_files = db.execute(
                "SELECT stored_name FROM uploads WHERE status='indexed'"
            ).fetchall()
        own = replace(
            settings, pdf_root=str(store.root / "uploads/files"), pdf_path_base=str(store.root)
        )
        preview_ready = any(
            resolve_pdf("uploads/files/" + r["stored_name"], own) is not None
            for r in uploaded_files
        )
        if not preview_ready and base and settings.pdf_root and Path(settings.pdf_root).is_dir():
            preview_ready = any(
                resolve_document_pdf(h["_source"], settings) is not None
                for h in scan(es, index=base, source=["paper_id", "source_file", "pdf_path"])
            )
        modules["pdf_preview"] = {
            "status": "ready"
            if preview_ready
            else "dependency_unavailable"
            if settings.pdf_root
            else "not_configured",
            "reason": "至少一篇PDF已核验可读；其余逐篇见pdf_available"
            if preview_ready
            else "PDF目录已配置但尚未找到可核验文件"
            if settings.pdf_root
            else "原始PDF目录未配置，文本检索可用",
        }
        try:
            with store.connect() as db:
                db.execute("SELECT count(*) FROM users").fetchone()
            local = {"status": "ready", "reason": "SQLite可读写；个人接口需登录"}
        except Exception:
            local = {"status": "dependency_unavailable", "reason": "SQLite尚未就绪"}
        for name in ("favorites", "history", "authentication", "uploads"):
            modules[name] = local
        for name in (
            "profile",
            "favorite_folders",
            "browsing_history",
            "ai_conversations",
            "notifications",
        ):
            modules[name] = local
        modules["password_recovery"] = {
            "status": "not_configured"
            if not os.getenv("EMAIL_BASE_URL")
            else "dependency_unavailable",
            "reason": "未配置邮件服务"
            if not os.getenv("EMAIL_BASE_URL")
            else "邮件端点已配置，以实际发送结果为准",
        }
        modules["pdf_to_docx"] = {
            "status": "ready",
            "reason": "本地文本PDF转换器已安装；文件可用性逐请求校验，扫描件需OCR",
        }
        modules["ai_stream"] = {
            "status": "ready"
            if configured and provider_verified(settings)
            else "not_configured"
            if not configured
            else "dependency_unavailable",
            "reason": "完整回答验证后分段SSE，不是上游逐token流",
        }
        grobid_ready = False
        if settings.grobid_url:
            try:
                r = httpx.get(
                    settings.grobid_url.rstrip("/") + "/api/isalive", timeout=2, trust_env=False
                )
                grobid_ready = r.status_code == 200 and r.text.strip().lower() == "true"
            except httpx.HTTPError:
                pass
        modules["upload_parsing"] = {
            "status": "ready"
            if grobid_ready
            else "dependency_unavailable"
            if settings.grobid_url
            else "not_configured",
            "reason": "GROBID健康检查成功"
            if grobid_ready
            else "GROBID未配置或健康检查失败；原始上传文件保留",
        }
        return {"modules": modules, "data_status": meta["data_status"]}

    @api.get("/metrics")
    def metrics():
        base, meta = metadata()
        base_count = es.count(index=base)["count"]
        uploaded = (
            es.count(index=settings.uploads_index)["count"]
            if es.indices.exists_alias(name=settings.uploads_index)
            else 0
        )
        vectors = {"status": "dependency_unavailable", "chunks": 0}
        try:
            generation, vector_meta = vector_metadata(es, settings, base)
            vectors = {
                "status": "ready",
                "chunks": es.count(index=generation)["count"],
                "model": vector_meta["model"],
                "model_revision": vector_meta["model_revision"],
                "dimensions": vector_meta["dimensions"],
                "chunk_version": vector_meta["chunk_version"],
                "generation": generation,
                "built_at": vector_meta.get("built_at"),
            }
        except Exception:
            pass
        try:
            uploaded_vectors = upload_vector_indices(es, settings)
            upload_vector_ready = bool(uploaded_vectors)
        except Exception:
            upload_vector_ready = False
        return {
            "base_papers": base_count,
            "approved_uploads": uploaded,
            "keyword_papers": base_count + uploaded,
            "base_mapping_version": meta["mapping_version"],
            "base_updated_at": meta["last_built_at"],
            "vector": vectors,
            "rrf_k": 60,
            "candidate_window": 1000,
            "semantic_scope": "base_and_vectorized_uploads",
            "uploaded_semantic_status": "ready" if upload_vector_ready else "not_vectorized",
            "precision_at_5": None,
            "ndcg_at_10": None,
        }

    @api.get("/evaluation")
    def evaluation():
        path = Path(settings.runtime_dir) / "search-evaluation.json"
        if not path.is_file():
            return {
                "status": "not_evaluated",
                "modes": {},
                "precision_at_5": None,
                "ndcg_at_10": None,
                "reason": "尚无实际评价记录或人工标注",
            }
        return json.loads(path.read_text(encoding="utf-8"))

    @api.get("/data-quality")
    def data_quality():
        base, meta = metadata()
        date_count = es.count(index=base, query={"exists": {"field": "date"}})["count"]
        year_count = es.count(index=base, query={"exists": {"field": "year"}})["count"]
        return {
            "indexed": es.count(index=base)["count"],
            "date_complete": date_count,
            "date_missing": es.count(index=base)["count"] - date_count,
            "year_present": year_count,
            "year_missing": es.count(index=base)["count"] - year_count,
            "date_filter_note": "date只包含完整YYYY-MM-DD；缺完整日期的论文仍可用year筛选，不能由year补造月份和日期",
            "status": meta["data_status"],
        }

    return api
