"""Suggestions and deterministic discovery derived from the current ES generation."""

import re
import secrets
import random
import threading
import time

from elasticsearch.helpers import scan
from fastapi import APIRouter, Query
from pydantic import BaseModel
from backend.api_models import PaperSummary


class Suggestion(BaseModel):
    text: str
    field: str
    paper_id: str


class SuggestResponse(BaseModel):
    query: str
    suggestions: list[Suggestion]


class ExampleSearch(BaseModel):
    q: str
    field: str


class YearBucket(BaseModel):
    year: int
    papers: int


class DiscoverResponse(BaseModel):
    papers: int
    recommendations: list[PaperSummary]
    example_searches: list[ExampleSearch]
    years: list[YearBucket]
    status: str


class RandomDiscoverResponse(BaseModel):
    seed: str
    recommendations: list[PaperSummary]
    excluded_count: int
    status: str


def router(es, metadata):
    api = APIRouter(prefix="/api")
    cache = {"generation": None, "expires": 0, "items": []}
    lock = threading.Lock()

    @api.get("/suggest", response_model=SuggestResponse)
    def suggest(
        q: str = Query(default="", max_length=200), limit: int = Query(default=8, ge=1, le=20)
    ):
        query = q.strip()
        if not query:
            return {"query": query, "suggestions": []}
        generation, _ = metadata()
        with lock:
            if cache["generation"] != generation or time.monotonic() > cache["expires"]:
                items = []
                for hit in scan(es, index=generation, source=["paper_id", "title", "authors"]):
                    doc = hit["_source"]
                    for field, values in [
                        ("title", [doc.get("title", "")]),
                        ("authors", doc.get("authors", [])),
                    ]:
                        items.extend(
                            {"text": v, "field": field, "paper_id": doc["paper_id"]}
                            for v in values
                            if v
                        )
                cache.update(
                    generation=generation,
                    expires=time.monotonic() + 60,
                    items=sorted(items, key=lambda d: (d["text"].casefold(), d["paper_id"])),
                )
            tokens = re.findall(r"\w+", query.casefold())
            if not tokens:
                return {"query": query, "suggestions": []}
            seen = set()
            results = []
            for item in cache["items"]:
                words = re.findall(r"\w+", item["text"].casefold())
                if (
                    all(any(w.startswith(t) for w in words) for t in tokens)
                    and item["text"].casefold() not in seen
                ):
                    seen.add(item["text"].casefold())
                    results.append(item)
                    if len(results) == limit:
                        break
        return {"query": query, "suggestions": results}

    @api.get("/discover", response_model=DiscoverResponse)
    def discover(limit: int = Query(default=6, ge=1, le=20)):
        generation, meta = metadata()
        response = es.search(
            index=generation,
            size=limit,
            sort=[{"year": {"order": "desc", "missing": "_last"}}, {"paper_id": "asc"}],
            source=["paper_id", "title", "authors", "affiliation", "year", "abstract"],
            aggs={"years": {"terms": {"field": "year", "size": 100, "order": {"_key": "desc"}}}},
            track_total_hits=True,
        )
        docs = [h["_source"] for h in response["hits"]["hits"]]
        return {
            "papers": response["hits"]["total"]["value"],
            "recommendations": docs,
            "example_searches": [{"q": d.get("title", ""), "field": "title"} for d in docs[:3]],
            "years": [
                {"year": b["key"], "papers": b["doc_count"]}
                for b in response["aggregations"]["years"]["buckets"]
            ],
            "status": meta["data_status"],
        }

    @api.get("/discover/random", response_model=RandomDiscoverResponse)
    def random_discover(
        limit: int = Query(default=3, ge=1, le=20),
        seed: str | None = Query(default=None, max_length=64),
        exclude: str = Query(default="", max_length=20000),
    ):
        generation, meta = metadata()
        excluded = {item for item in (part.strip() for part in exclude.split(",")) if item}
        actual_seed = seed or secrets.token_hex(12)
        rng = random.Random(actual_seed)
        docs = [
            h["_source"]
            for h in scan(
                es,
                index=generation,
                source=["paper_id", "title", "authors", "affiliation", "year", "abstract"],
            )
        ]
        candidates = [doc for doc in docs if doc["paper_id"] not in excluded]
        if len(candidates) < limit:
            candidates = docs
        rng.shuffle(candidates)
        return {
            "seed": actual_seed,
            "recommendations": candidates[:limit],
            "excluded_count": len(excluded),
            "status": meta["data_status"],
        }

    return api
