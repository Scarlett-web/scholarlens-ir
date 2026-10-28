"""Paper-level dense retrieval and reciprocal rank fusion over bounded candidates."""

from functools import lru_cache
import html
import time

from fastapi import HTTPException

from backend.embeddings import Encoder, MODEL, REVISION

WINDOW = 1000
RRF_K = 60


def unavailable(code="dependency_unavailable", message="检索依赖尚未就绪"):
    return HTTPException(503, detail={"code": code, "message": message, "details": {}})


@lru_cache(maxsize=2)
def encoder(root: str) -> Encoder:
    return Encoder(root)


def vector_metadata(es, settings, base: str) -> tuple[str, dict]:
    mappings = es.indices.get_mapping(index=settings.vector_index)
    if len(mappings) != 1:
        raise unavailable()
    generation, definition = next(iter(mappings.items()))
    meta = definition["mappings"].get("_meta", {})
    if meta.get("base_generation") != base or meta.get("model_revision") != REVISION:
        raise unavailable(message="向量索引与当前论文版本不一致，请重新构建独立向量索引")
    return generation, meta


def upload_vector_indices(es, settings) -> list[str]:
    if not es.indices.exists_alias(name=settings.upload_vector_index):
        return []
    if not es.indices.exists_alias(name=settings.uploads_index):
        return []
    source = list(es.indices.get_alias(name=settings.uploads_index))
    mappings = es.indices.get_mapping(index=settings.upload_vector_index)
    if len(source) != 1 or len(mappings) != 1:
        raise unavailable(message="上传向量与论文版本不一致")
    meta = next(iter(mappings.values()))["mappings"].get("_meta", {})
    if meta.get("base_generation") != source[0] or meta.get("model_revision") != REVISION:
        raise unavailable(message="上传向量需要重新构建，关键词检索仍可使用")
    return list(mappings)


def uploaded_papers(es, settings):
    return (
        list(es.indices.get_alias(name=settings.uploads_index))
        if es.indices.exists_alias(name=settings.uploads_index)
        else []
    )


def vector_candidates(
    es, settings, base: str, params, paper_ids=None, collapse_papers=True, chunk_limit=100
):
    generation, meta = vector_metadata(es, settings, base)
    try:
        vector = encoder(settings.model_dir).encode([params.q])[0]
    except (OSError, ValueError, ImportError):
        raise unavailable(message="本地嵌入模型缺失或验证失败")
    filters = []
    years = {}
    if params.year_from is not None:
        years["gte"] = params.year_from
    if params.year_to is not None:
        years["lte"] = params.year_to
    if years:
        filters.append({"range": {"year": years}})
    if params.field != "all":
        filters.append({"term": {"field": params.field}})
    if paper_ids is not None:
        filters.append({"terms": {"paper_id": paper_ids}})
    aggregation = {"collapse": {"field": "paper_id"}} if collapse_papers else {}
    vector_indices = [generation, *upload_vector_indices(es, settings)]
    result = es.search(
        index=vector_indices,
        size=WINDOW if collapse_papers else min(chunk_limit, 200),
        query={
            "script_score": {
                "query": {"bool": {"filter": filters}},
                "script": {
                    "source": "cosineSimilarity(params.vector, 'embedding') + 1.0",
                    "params": {"vector": vector},
                },
            }
        },
        sort=[{"_score": "desc"}, {"paper_id": "asc"}, {"chunk_id": "asc"}],
        source_excludes=["embedding"],
        track_total_hits=True,
        **aggregation,
    )
    return result["hits"]["hits"], meta


def rrf(keyword: list[str], dense: list[str], k: int = RRF_K) -> list[tuple[str, float]]:
    """Fuse one rank per paper per list, never adding raw lexical/cosine scores."""
    scores = {}
    for items in (keyword, dense):
        for rank, paper in enumerate(dict.fromkeys(items), 1):
            scores[paper] = scores.get(paper, 0) + 1 / (k + rank)
    return sorted(scores.items(), key=lambda p: (-p[1], p[0]))


def validate_extended(params):
    """Validate mode-specific inputs before contacting an external dependency."""
    if params.mode == "semantic" and (
        params.field not in ("all", "title", "fulltext") or params.phrase or params.fuzzy
    ):
        raise HTTPException(
            400,
            detail={
                "code": "invalid_parameter",
                "message": "semantic支持all/title/fulltext，短语和模糊参数仅适用于关键词侧",
                "details": {},
            },
        )
    if params.page * params.page_size > WINDOW:
        raise HTTPException(
            400,
            detail={
                "code": "invalid_parameter",
                "message": "语义/混合候选分页窗口上限1000",
                "details": {},
            },
        )


def search_extended(es, settings, base, params, build_search):
    """Run dense/dual retrieval; keyword-only parameters never silently ignored."""
    started = time.monotonic()
    validate_extended(params)
    # For hybrid metadata fields, dense uses all text; keyword retains exact chosen field.
    dense_params = params.model_copy(
        update={"field": params.field if params.field in ("title", "fulltext") else "all"}
    )
    dense, meta = vector_candidates(es, settings, base, dense_params)
    keyword = []
    if params.mode == "hybrid":
        body = build_search(params)
        body.update(from_=0, size=WINDOW, sort=[{"_score": "desc"}, {"paper_id": "asc"}])
        keyword = es.search(index=[base, *uploaded_papers(es, settings)], **body)["hits"]["hits"]
    dense_ids = [h["_source"]["paper_id"] for h in dense]
    keyword_ids = [h["_source"]["paper_id"] for h in keyword]
    ranked = (
        rrf(keyword_ids, dense_ids)
        if params.mode == "hybrid"
        else [(h["_source"]["paper_id"], h["_score"]) for h in dense]
    )
    if not ranked:
        return {
            "query": params.model_dump(),
            "total": 0,
            "page": params.page,
            "page_size": params.page_size,
            "took_ms": int((time.monotonic() - started) * 1000),
            "results": [],
        }
    docs = {}
    base_ids = [p for p, _ in ranked]
    for index_name in [base, *uploaded_papers(es, settings)]:
        for d in es.mget(
            index=index_name,
            ids=base_ids,
            source_includes=["paper_id", "title", "authors", "year", "date", "affiliation", "address", "abstract"],
        )["docs"]:
            if d.get("found"):
                docs[d["_id"]] = d["_source"]
    ranked = [entry for entry in ranked if entry[0] in docs]
    if params.sort != "relevance":
        ranked.sort(
            key=lambda p: (
                docs[p[0]].get("year") is None,
                (
                    -(docs[p[0]].get("year") or 0)
                    if params.sort == "year_desc"
                    else docs[p[0]].get("year") or 0
                ),
                -p[1],
                p[0],
            )
        )
    dense_map = {h["_source"]["paper_id"]: h["_source"] for h in dense}
    keyword_map = {h["_source"]["paper_id"]: h for h in keyword}
    dense_ranks = {p: i for i, p in enumerate(dense_ids, 1)}
    keyword_ranks = {p: i for i, p in enumerate(keyword_ids, 1)}
    hits = []
    offset = (params.page - 1) * params.page_size
    for paper, score in ranked[offset : offset + params.page_size]:
        doc = docs[paper]
        chunk = dense_map.get(paper)
        lexical = keyword_map.get(paper, {})
        explanation = {
            "retrieval": "rrf" if params.mode == "hybrid" else "dense_cosine",
            "reason": "候选论文级排名；语义分数不是精确词项命中",
            "model_name": MODEL,
            "model_revision": meta["model_revision"],
            "vector_rank": str(dense_ranks.get(paper, "")),
            "keyword_rank": str(keyword_ranks.get(paper, "")),
            "candidate_window": str(WINDOW),
        }
        if params.mode == "hybrid":
            explanation.update(rrf_k=str(RRF_K), rrf_score=str(score))
        if chunk:
            explanation.update(
                chunk_id=chunk["chunk_id"], locator=chunk["locator"], evidence=chunk["text"][:900]
            )
        from backend.search_text import search_highlights
        highlights = lexical.get("highlight", {})
        # Semantic snippets are escaped text without false exact-match emphasis.
        if not highlights and chunk:
            highlights = {chunk["field"]: [html.escape(chunk["text"][:240])]}
        highlights = search_highlights(highlights, title=doc.get("title", ""), query=params.q, field=params.field)
        hits.append(
            {
                "paper_id": paper,
                "title": doc.get("title", ""),
                "authors": doc.get("authors", []),
                "year": doc.get("year"),
                "date": doc.get("date", ""),
                "affiliation": doc.get("affiliation", []),
                "address": doc.get("address", []),
                "abstract_snippet": doc.get("abstract", "")[:240],
                "highlights": highlights,
                "score": score,
                "matched_fields": lexical.get("matched_queries", [])
                if lexical
                else ([chunk["field"]] if chunk else []),
                "explanation": explanation,
            }
        )
    return {
        "query": params.model_dump(),
        "total": len(ranked),
        "page": params.page,
        "page_size": params.page_size,
        "took_ms": int((time.monotonic() - started) * 1000),
        "results": hits,
    }
