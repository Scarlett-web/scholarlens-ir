"""Public response shapes; filesystem and parser error strings stay private."""

from typing import Any, Literal, Generic, TypeVar

from pydantic import BaseModel, Field

from backend.schema import Pages


class SearchHit(BaseModel):
    paper_id: str
    title: str
    authors: list[str]
    year: int | None
    abstract_snippet: str
    highlights: dict[str, list[str]]
    score: float
    matched_fields: list[str]
    explanation: dict[str, str]


class SearchResponse(BaseModel):
    query: dict[str, Any]
    total: int
    page: int
    page_size: int
    took_ms: int
    results: list[SearchHit]


class SourceStatus(BaseModel):
    pdf: Literal["available", "pdf_not_available"]
    parse_status: Literal["success", "partial", "error", "unknown"]


class PaperDetail(BaseModel):
    paper_id: str
    title: str
    authors: list[str]
    date: str
    year: int | None
    affiliation: list[str]
    address: list[str]
    abstract: str
    fulltext: str
    pages: Pages | None
    pdf_available: bool
    source_status: SourceStatus
    chunks: list[dict]  # P0 has no chunk pipeline; always empty.
    available_actions: list[Literal["view_pdf"]]
    source_info: dict[str, Any] = Field(default_factory=dict)
    quality: dict[str, Any] = Field(default_factory=dict)


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    total: int
    page: int
    page_size: int
    results: list[T]


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorDetail


class ContentResponse(BaseModel):
    paper_id: str
    offset: int
    limit: int
    total_characters: int
    text: str
    has_more: bool
    locator: str


class StatsResponse(BaseModel):
    papers: int
    indexed: int
    fields_completeness: dict[str, float]
    parser: dict[str, int]
    index: dict[str, str]
    status: str


class PaperSummary(BaseModel):
    paper_id: str
    title: str
    authors: list[str]
    affiliation: list[str] = Field(default_factory=list)
    year: int | None
    abstract: str


class ChunkResponse(BaseModel):
    chunk_id: str
    paper_id: str
    title: str
    field: Literal["title", "abstract", "fulltext"]
    offset_start: int
    offset_end: int
    locator: str
    text: str
    year: int | None
