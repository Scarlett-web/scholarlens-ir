"""Validate JSONL input independently of Elasticsearch; never modify sources."""

import datetime as dt
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SEARCH_FIELDS = ("title", "authors", "date", "affiliation", "address", "fulltext")


class Pages(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    first: int | None = Field(default=None, ge=1)
    last: int | None = Field(default=None, ge=1)
    count: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def check_range(self) -> "Pages":
        if self.first is not None and self.last is not None and self.last < self.first:
            raise ValueError("pages.last precedes pages.first")
        return self


class Paper(BaseModel):
    """Core schema plus optional parser diagnostics; malformed input raises ValueError."""

    model_config = ConfigDict(strict=True, extra="forbid")
    paper_id: str = Field(min_length=1, max_length=512)
    title: str = ""
    authors: list[str] = Field(default_factory=list)
    date: str = ""
    year: int | None = Field(default=None, ge=1, le=9999)
    affiliation: list[str] = Field(default_factory=list)
    address: list[str] = Field(default_factory=list)
    pages: Pages | None = None
    abstract: str = ""
    fulltext: str = ""
    pdf_path: str = ""
    source_file: str = ""
    parse_status: Literal["success", "partial", "error"] | None = None
    errors: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_identity_and_date(self) -> "Paper":
        if self.paper_id != self.paper_id.strip():
            raise ValueError("paper_id has surrounding whitespace")
        if len(self.paper_id.encode("utf-8")) > 512:
            raise ValueError("paper_id exceeds Elasticsearch byte limit")
        if self.date:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", self.date):
                raise ValueError("date must be YYYY-MM-DD or empty")
            parsed = dt.date.fromisoformat(self.date)
            if self.year is not None and parsed.year != self.year:
                raise ValueError("date and year disagree")
        return self

    def index_document(self) -> dict:
        """Return a derived index document, excluding empty date and unsafe body text."""
        doc = self.model_dump()
        doc["parse_status"] = self.parse_status or "unknown"
        if not self.date:
            del doc["date"]
        else:
            doc["date_value"] = self.date
        if "unreadable_characters_in_fulltext" in self.errors or "\ufffd" in self.fulltext:
            doc["fulltext"] = ""
        return doc
