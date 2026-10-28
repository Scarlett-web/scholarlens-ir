"""FastAPI six-field keyword search backed by a real Elasticsearch node."""

from contextlib import asynccontextmanager
from typing import Literal

from elastic_transport import TransportError
from elasticsearch import ApiError, NotFoundError
from fastapi import Depends, FastAPI, HTTPException, Response, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.api_models import (
    PaperDetail,
    SearchResponse,
    StatsResponse,
    ContentResponse,
    ErrorResponse,
    Page,
    ChunkResponse,
)
from fastapi.openapi.utils import get_openapi
from backend.config import Settings, make_client
from backend.pdf_access import resolve_pdf, resolve_document_pdf
from backend.schema import SEARCH_FIELDS
from backend.search_text import has_cjk, search_highlights, highlight_query_text
from backend.discovery import router as discovery_router
from backend.retrieval import search_extended, validate_extended
from backend.accounts import Store, router as accounts_router
from backend.rag import router as rag_router
from backend.capabilities import router as capabilities_router
from backend.uploads import router as uploads_router
from backend.workspace import router as workspace_router
from backend.web import mount_frontend
from backend.docx_convert import router as docx_router
from backend.email_codes import router as email_router
from dataclasses import replace
from backend.request_limits import UploadLimitMiddleware
from backend.pdf_response import PDFResponse
from backend.chunks import chunks
from backend.retrieval import vector_metadata, upload_vector_indices
import re
from pathlib import PureWindowsPath

WEIGHTS = {"title": 3, "authors": 2, "date": 1, "affiliation": 1, "address": 1, "fulltext": 1}


class SearchParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    q: str = Field(min_length=1, max_length=500)
    field: Literal["all", "title", "authors", "date", "affiliation", "address", "fulltext"] = "all"
    mode: Literal["keyword", "semantic", "hybrid"] = "keyword"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    sort: Literal["relevance", "year_desc", "year_asc"] = "relevance"
    year_from: int | None = Field(default=None, ge=1, le=9999)
    year_to: int | None = Field(default=None, ge=1, le=9999)
    phrase: bool = False
    fuzzy: bool = False


def build_search(params: SearchParams) -> dict:
    """Translate validated parameters into bounded BM25 DSL and named hit fields."""
    fields = list(SEARCH_FIELDS) if params.field == "all" else [params.field]
    match_options = {"query": params.q, "operator": "and"}
    if params.fuzzy:
        match_options.update(fuzziness="AUTO", prefix_length=1, max_expansions=25)
    multi = {
        **match_options,
        "fields": [f"{field}^{WEIGHTS[field]}" for field in fields],
        "type": "phrase" if params.phrase else "best_fields",
    }
    cross_field = params.field == "all" and not params.phrase
    lexical_query = {"multi_match": multi}
    if cross_field:
        if params.fuzzy:
            lexical_query = {
                "bool": {
                    "must": [{"multi_match": {**multi, "query": word}} for word in params.q.split()]
                }
            }
        else:
            lexical_query = {"multi_match": {**multi, "type": "cross_fields"}}
    named = []
    for field in fields:
        options = {"query": params.q, "_name": field}
        if not params.phrase:
            options.update({k: v for k, v in match_options.items() if k != "query"})
            if cross_field:
                options["operator"] = "or"
        match = {"match_phrase" if params.phrase else "match": {field: options}}
        named.append({"constant_score": {"filter": match, "boost": 0}})
    cjk = has_cjk(params.q)
    if cjk:
        # Auxiliary fields may be absent in legacy generations: keep their standard path.
        cjk_query = {"multi_match": {"query": params.q,
            "fields": [f"{field}.cjk^{WEIGHTS[field]}" for field in fields],
            "type": "phrase" if params.phrase else "best_fields", "operator": "and"}}
        lexical_query = {"bool": {"should": [lexical_query, cjk_query], "minimum_should_match": 1}}
        named.extend({"constant_score": {"filter": {"match": {field + ".cjk": {
            "query": params.q, "_name": field + ".cjk"}}}, "boost": 0}} for field in fields)
    query = {"must": [lexical_query], "should": named}
    year_range = {}
    if params.year_from is not None:
        year_range["gte"] = params.year_from
    if params.year_to is not None:
        year_range["lte"] = params.year_to
    if year_range:
        query["filter"] = [{"range": {"year": year_range}}]
    sort = [{"_score": "desc"}, {"paper_id": "asc"}]
    if params.sort != "relevance":
        sort.insert(
            0,
            {
                "year": {
                    "order": "desc" if params.sort == "year_desc" else "asc",
                    "missing": "_last",
                }
            },
        )
    highlight_fields = [*fields, *([field + ".cjk" for field in fields] if cjk else [])]
    highlight_query = {"multi_match": {
        **multi, "query": highlight_query_text(params.q, phrase=params.phrase),
        "fields": highlight_fields, "operator": "or",
    }}
    return {
        "query": {"bool": query},
        "from_": (params.page - 1) * params.page_size,
        "size": params.page_size,
        "sort": sort,
        "track_total_hits": True,
        "track_scores": True,
        "_source": ["paper_id", "title", "authors", "year", "date", "affiliation", "address", "abstract"],
        "highlight": {
            "encoder": "html",
            "max_analyzed_offset": 1000000,
            "pre_tags": ["<em>"],
            "post_tags": ["</em>"],
            "highlight_query": highlight_query,
            "order": "score",
            "fields": {field: ({"number_of_fragments": 2, "fragment_size": 180}
                               if field.removesuffix(".cjk") == "fulltext" else {"number_of_fragments": 0})
                       for field in highlight_fields},
        },
    }


def create_app(settings: Settings | None = None, client=None) -> FastAPI:
    settings = settings or Settings.from_env()
    owns_client = client is None
    es = client if client is not None else make_client(settings)

    @asynccontextmanager
    async def lifespan(app):
        yield
        if owns_client:
            es.close()

    app = FastAPI(
        title="ScholarLens",
        version="0.2.1",
        lifespan=lifespan,
        responses={
            status: {"model": ErrorResponse}
            for status in (400, 401, 403, 404, 409, 413, 429, 500, 502, 503, 504)
        },
    )
    store = Store(settings.runtime_dir)
    app.add_middleware(UploadLimitMiddleware, store=store)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[v.strip() for v in settings.cors_origins.split(",") if v.strip()],
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type"],
            expose_headers=["X-ScholarLens-Data-Status"],
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "invalid_parameter",
                    "message": "请求参数不符合契约",
                    "details": {"fields": [".".join(map(str, e["loc"])) for e in exc.errors()]},
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        code = {404: "not_found", 405: "method_not_allowed"}.get(
            exc.status_code, "invalid_parameter"
        )
        detail = (
            exc.detail
            if isinstance(exc.detail, dict)
            else {"code": code, "message": str(exc.detail), "details": {}}
        )
        return JSONResponse(
            status_code=exc.status_code, content={"error": detail}, headers=exc.headers
        )

    @app.exception_handler(ApiError)
    @app.exception_handler(TransportError)
    async def es_error(request, exc):
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "dependency_unavailable",
                    "message": "Elasticsearch 或论文索引暂未就绪",
                    "details": {},
                }
            },
        )

    @app.exception_handler(Exception)
    async def internal_error(request, exc):
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "服务内部错误", "details": {}}},
        )

    def metadata() -> tuple[str, dict]:
        mappings = es.indices.get_mapping(index=settings.index)
        if len(mappings) != 1:
            raise HTTPException(
                503,
                detail={
                    "code": "dependency_unavailable",
                    "message": "论文别名必须指向单个索引",
                    "details": {},
                },
            )
        meta = next(iter(mappings.values()))["mappings"].get("_meta", {})
        if meta.get("data_status") not in ("mock", "real") or "input_records" not in meta:
            raise HTTPException(
                503,
                detail={
                    "code": "dependency_unavailable",
                    "message": "索引缺少导入元数据",
                    "details": {},
                },
            )
        return next(iter(mappings)), meta

    def upload_indices():
        if settings.index.endswith("-real") and es.indices.exists_alias(
            name=settings.uploads_index
        ):
            return list(es.indices.get_alias(name=settings.uploads_index))
        return []

    def document_pdf(doc):
        if doc["paper_id"].startswith("upload-sha256:"):
            with store.connect() as db:
                row = db.execute(
                    "SELECT stored_name FROM uploads WHERE paper_id=? AND status='indexed' LIMIT 1",
                    (doc["paper_id"],),
                ).fetchone()
            if row:
                own_settings = replace(
                    settings,
                    pdf_root=str(store.root / "uploads/files"),
                    pdf_path_base=str(store.root),
                )
                return resolve_pdf("uploads/files/" + row["stored_name"], own_settings)
            return None
        return resolve_document_pdf(doc, settings)

    def upload_lookup(upload_id, user):
        with store.connect() as db:
            row = db.execute("SELECT * FROM uploads WHERE id=?", (upload_id,)).fetchone()
        if row is None or (row["user_id"] != user["id"] and user.get("role") != "admin"):
            raise HTTPException(
                404, detail={"code": "not_found", "message": "上传记录不存在", "details": {}}
            )
        if row["status"] not in ("pending", "approved", "processing", "indexed"):
            raise HTTPException(
                409, detail={"code": "invalid_state", "message": "上传尚未允许下载", "details": {}}
            )
        return row

    @app.get("/api/search", response_model=SearchResponse)
    def search(response: Response, params: SearchParams = Depends()):
        params.q = params.q.strip()
        if (
            not params.q
            or params.page * params.page_size > 10000
            or (
                params.year_from is not None
                and params.year_to is not None
                and params.year_from > params.year_to
            )
            or (params.phrase and params.fuzzy)
            or (params.fuzzy and len(params.q.split()) > 20)
        ):
            raise HTTPException(
                400,
                detail={
                    "code": "invalid_parameter",
                    "message": "查询、分页或筛选范围无效",
                    "details": {},
                },
            )
        if params.mode != "keyword":
            validate_extended(params)
        generation, meta = metadata()
        response.headers["X-ScholarLens-Data-Status"] = meta["data_status"]
        if params.mode != "keyword":
            return search_extended(es, settings, generation, params, build_search)
        result = es.search(index=[generation, *upload_indices()], **build_search(params))
        hits = []
        for hit in result["hits"]["hits"]:
            doc = hit["_source"]
            matched = [field for field in SEARCH_FIELDS if field in hit.get("matched_queries", [])
                       or field + ".cjk" in hit.get("matched_queries", [])]
            hits.append(
                {
                    "paper_id": doc["paper_id"],
                    "title": doc.get("title", ""),
                    "authors": doc.get("authors", []),
                    "year": doc.get("year"),
                    "date": doc.get("date", ""),
                    "affiliation": doc.get("affiliation", []),
                    "address": doc.get("address", []),
                    "abstract_snippet": doc.get("abstract", "")[:240],
                    "highlights": search_highlights(hit.get("highlight", {}),
                        title=doc.get("title", ""), query=params.q, field=params.field),
                    "score": hit.get("_score"),
                    "matched_fields": matched,
                    "explanation": {"retrieval": "bm25", "reason": ", ".join(matched) + " match"},
                }
            )
        return {
            "query": params.model_dump(),
            "total": result["hits"]["total"]["value"],
            "page": params.page,
            "page_size": params.page_size,
            "took_ms": result["took"],
            "results": hits,
        }

    @app.get("/api/stats", response_model=StatsResponse)
    def stats(response: Response):
        generation, meta = metadata()
        response.headers["X-ScholarLens-Data-Status"] = meta["data_status"]
        return {
            "papers": meta["input_records"],
            "indexed": es.count(index=generation)["count"],
            "fields_completeness": meta["fields_completeness"],
            "parser": meta["parser"],
            "index": {
                "last_built_at": meta["last_built_at"],
                "mapping_version": meta["mapping_version"],
            },
            "status": meta["data_status"],
        }

    def read_paper(paper_id: str) -> tuple[dict, dict]:
        """Read by the imported _id; distinguish missing paper from unavailable index."""
        if (
            not paper_id.strip()
            or paper_id != paper_id.strip()
            or len(paper_id.encode("utf-8")) > 512
            or any(c in paper_id for c in ("/", "\\"))
            or any(ord(c) < 32 or ord(c) == 127 for c in paper_id)
        ):
            raise HTTPException(
                400,
                detail={"code": "invalid_parameter", "message": "paper_id 格式无效", "details": {}},
            )
        generation, meta = metadata()
        try:
            hit = es.get(index=generation, id=paper_id)
        except NotFoundError as exc:
            # Missing index is still a dependency error (e.g. external deletion).
            if isinstance(exc.body, dict) and "error" in exc.body:
                raise
            for extra in upload_indices():
                try:
                    hit = es.get(index=extra, id=paper_id)
                    return hit["_source"], meta
                except NotFoundError:
                    pass
            raise HTTPException(
                404, detail={"code": "paper_not_found", "message": "论文不存在", "details": {}}
            ) from exc
        return hit["_source"], meta

    # Register the PDF route before the path-converter detail route.
    @app.get(
        "/api/papers/{paper_id:path}/pdf",
        response_class=FileResponse,
        responses={
            200: {
                "description": "已交付原始 PDF",
                "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
            },
            404: {"description": "paper_not_found 或 pdf_not_available"},
            416: {"model": ErrorResponse, "description": "range_not_satisfiable"},
        },
    )
    def paper_pdf(paper_id: str):
        doc, meta = read_paper(paper_id)
        pdf = document_pdf(doc)
        if pdf is None:
            raise HTTPException(
                404,
                detail={
                    "code": "pdf_not_available",
                    "message": "原始 PDF 尚未交付或暂不可访问",
                    "details": {},
                },
            )
        return PDFResponse(
            pdf,
            media_type="application/pdf",
            filename="paper.pdf",
            content_disposition_type="inline",
            headers={
                "X-ScholarLens-Data-Status": meta["data_status"],
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app.get("/api/papers/{paper_id:path}/content", response_model=ContentResponse)
    def paper_content(
        paper_id: str,
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=8000, ge=1, le=20000),
    ):
        doc, _ = read_paper(paper_id)
        text = doc.get("fulltext", "")
        return {
            "paper_id": paper_id,
            "offset": offset,
            "limit": limit,
            "total_characters": len(text),
            "text": text[offset : offset + limit],
            "has_more": offset + limit < len(text),
            "locator": f"fulltext:chars:{min(offset, len(text))}-{min(offset + limit, len(text))}",
        }

    @app.get("/api/papers/{paper_id:path}/chunks", response_model=Page[ChunkResponse])
    def paper_chunks(
        paper_id: str,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
    ):
        doc, _ = read_paper(paper_id)
        values = chunks(doc)
        return {
            "total": len(values),
            "page": page,
            "page_size": page_size,
            "results": values[(page - 1) * page_size : page * page_size],
        }

    @app.get("/api/chunks/{chunk_id}", response_model=ChunkResponse)
    def chunk_detail(chunk_id: str):
        if not re.fullmatch(r"chunk:[a-f0-9]{64}", chunk_id):
            raise HTTPException(
                400,
                detail={"code": "invalid_parameter", "message": "chunk_id格式无效", "details": {}},
            )
        base, _ = metadata()
        generations = upload_vector_indices(es, settings)
        try:
            vector_generation, _ = vector_metadata(es, settings, base)
            generations = [vector_generation, *generations]
        except (HTTPException, NotFoundError):
            if not generations:
                raise
        hit = None
        for generation in generations:
            try:
                hit = es.get(index=generation, id=chunk_id, source_excludes=["embedding"])
                break
            except NotFoundError:
                continue
        if hit is None:
            raise HTTPException(
                404, detail={"code": "chunk_not_found", "message": "片段不存在", "details": {}}
            )
        c = hit["_source"]
        doc, _ = read_paper(c["paper_id"])
        if doc.get(c["field"], "")[c["offset_start"] : c["offset_end"]] != c["text"]:
            raise HTTPException(
                503,
                detail={
                    "code": "dependency_unavailable",
                    "message": "片段与当前论文版本不一致",
                    "details": {},
                },
            )
        return c

    app.include_router(docx_router(settings, store, read_paper, document_pdf, upload_lookup))

    @app.get("/api/papers/{paper_id:path}", response_model=PaperDetail)
    def paper_detail(paper_id: str, response: Response, include_fulltext: bool = True):
        doc, meta = read_paper(paper_id)
        response.headers["X-ScholarLens-Data-Status"] = meta["data_status"]
        available = document_pdf(doc) is not None
        return {
            "paper_id": doc["paper_id"],
            "title": doc.get("title", ""),
            "authors": doc.get("authors", []),
            "date": doc.get("date", ""),
            "year": doc.get("year"),
            "affiliation": doc.get("affiliation", []),
            "address": doc.get("address", []),
            "abstract": doc.get("abstract", ""),
            "fulltext": doc.get("fulltext", "") if include_fulltext else "",
            "pages": doc.get("pages"),
            "pdf_available": available,
            "source_status": {
                "pdf": "available" if available else "pdf_not_available",
                "parse_status": doc.get("parse_status") or "unknown",
            },
            "chunks": [],
            "available_actions": ["view_pdf"] if available else [],
            "source_info": {
                "filename": PureWindowsPath(doc.get("source_file", "")).name,
                "fulltext_characters": len(doc.get("fulltext", "")),
            },
            "quality": {
                "parse_status": doc.get("parse_status") or "unknown",
                "body_quarantined": "unreadable_characters_in_fulltext" in doc.get("errors", []),
                "missing_fields": [f for f in SEARCH_FIELDS if not doc.get(f)],
            },
        }

    app.include_router(discovery_router(es, metadata))
    app.include_router(accounts_router(store, read_paper))
    app.include_router(workspace_router(store, read_paper))
    app.include_router(email_router(store))
    app.include_router(rag_router(es, settings, metadata, read_paper, upload_indices, store))
    app.include_router(capabilities_router(es, settings, metadata, store))
    app.include_router(uploads_router(es, settings, store))

    def openapi():
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
        for path in schema["paths"].values():
            for operation in path.values():
                if isinstance(operation, dict):
                    operation.get("responses", {}).pop("422", None)
        app.openapi_schema = schema
        return schema

    app.openapi = openapi
    mount_frontend(app, settings.frontend_dir)
    return app


app = create_app()
