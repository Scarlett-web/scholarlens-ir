"""Bounded, corpus-derived English spelling candidates; never rewrites a query."""

import re
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

FIELDS = Literal["all", "title", "authors", "date", "affiliation", "address", "fulltext"]


def edit_distance(left: str, right: str) -> int:
    """Optimal-string-alignment distance, including adjacent transpositions."""
    rows = [list(range(len(right) + 1))]
    for i, a in enumerate(left, 1):
        row = [i]
        for j, b in enumerate(right, 1):
            value = min(row[j - 1] + 1, rows[-1][j] + 1, rows[-1][j - 1] + (a != b))
            if i > 1 and j > 1 and a == right[j - 2] and left[i - 2] == b:
                value = min(value, rows[-2][j - 2] + 1)
            row.append(value)
        rows.append(row)
    return rows[-1][-1]


def corrections(
    es, generation, q, field, year_from, year_to, limit, build_query, require_empty=True
):
    """Return at most three verified candidates; perform no index mutations.

    English whitespace queries only. ES errors propagate to the application's
    normal dependency handler; callers may treat suggestions as optional.
    """
    text = q.strip()
    if field in ("authors", "date") or not re.fullmatch(r"[A-Za-z ]{4,200}", text):
        return []
    words = list(re.finditer(r"[A-Za-z]+", text))
    if not 1 <= len(words) <= 8:
        return []

    def hits(value):
        body = build_query(value, field, year_from, year_to)
        return es.count(index=generation, query=body["query"])["count"]

    original_matches = hits(text)
    if original_matches and require_empty:
        return []
    eligible = [(i, m) for i, m in enumerate(words) if len(m[0]) >= 3 and not m[0].isupper()]
    if not eligible:
        return []
    term_field = "title" if field == "all" else field
    verified = {}
    attempted = set()
    budget = 36

    def verify(value, cost):
        nonlocal budget
        key = value.casefold()
        if key == text.casefold() or key in attempted or budget <= 0:
            return
        attempted.add(key)
        budget -= 1
        count = hits(value)
        if count:
            verified[key] = (
                {"text": value, "field": field, "kind": "spelling", "matched_count": count},
                cost,
            )

    # Prioritize clear space errors before alternative spellings spend the budget.
    for left, right in zip(words, words[1:]):
        if (
            min(len(left[0]), len(right[0])) <= 4
            and not left[0].isupper()
            and not right[0].isupper()
        ):
            verify(text[: left.end()] + text[right.start() :], 1)
    if len(words) == 1 and 7 <= len(words[0][0]) <= 24:
        for split in range(3, len(text) - 2):
            verify(text[:split] + " " + text[split:], 1)
    if verified:
        return [
            item[0]
            for item in sorted(
                verified.values(), key=lambda item: (-item[0]["matched_count"], item[0]["text"])
            )[:limit]
        ]

    if original_matches:
        return []

    # Missing-term candidates solve ordinary typos first. Always-mode is a
    # bounded second pass for valid words used in an otherwise empty query.
    for suggest_mode in ("missing", "always"):
        suggest = {
            str(i): {
                "text": match[0].lower(),
                "term": {
                    "field": term_field,
                    "suggest_mode": suggest_mode,
                    "size": 5,
                    "max_edits": 2 if len(match[0]) >= 5 else 1,
                    "prefix_length": 0,
                    "min_word_length": 3,
                },
            }
            for i, match in eligible
        }
        if field == "all":
            suggest.update(
                {
                    key + "_body": {
                        "text": value["text"],
                        "term": {**value["term"], "field": "fulltext"},
                    }
                    for key, value in list(suggest.items())
                }
            )
        response = es.search(index=generation, size=0, suggest=suggest)
        changes = []
        for i, match in eligible:
            entries = response.get("suggest", {}).get(str(i), []) + response.get("suggest", {}).get(
                str(i) + "_body", []
            )
            options = []
            for option in [item for entry in entries for item in entry.get("options", [])]:
                value = option["text"]
                if (
                    option["score"] >= 0.5
                    and re.fullmatch(r"[a-z]{3,}", value)
                    and value != match[0].lower()
                ):
                    distance = edit_distance(match[0].lower(), value)
                    if distance <= (2 if len(match[0]) >= 5 else 1):
                        options.append((value, distance, option.get("freq", 0)))
            options = sorted(
                {o[0]: o for o in sorted(options, key=lambda o: o[2])}.values(),
                key=lambda o: (o[1], -o[2], o[0]),
            )
            if options:
                if suggest_mode == "always":
                    options = [(match[0], 0, 0), *options]
                changes.append((i, options[:6]))
        if 0 < len(changes) <= 3:
            # Keep only a small beam rather than materializing exponential combinations.
            beam = [([], 0, 0)]
            for _, options in changes:
                beam = sorted(
                    [
                        (chosen + [value], cost + distance, freq + frequency)
                        for chosen, cost, freq in beam
                        for value, distance, frequency in options
                    ],
                    key=lambda item: (item[1], -item[2], item[0]),
                )[:36]
            for chosen, cost, _ in beam:
                value = text
                for (i, _), replacement in reversed(list(zip(changes, chosen, strict=True))):
                    match = words[i]
                    value = value[: match.start()] + replacement + value[match.end() :]
                verify(value, cost)
        if verified or budget <= 0:
            break

    if not verified:
        # Space edits use the same corpus validation, never a fixed phrase table.
        for left, right in zip(words, words[1:]):
            if (
                min(len(left[0]), len(right[0])) <= 4
                and not left[0].isupper()
                and not right[0].isupper()
            ):
                verify(text[: left.end()] + text[right.start() :], 1)
        for _, match in eligible:
            if not 7 <= len(match[0]) <= 24:
                continue
            for split in range(3, len(match[0]) - 2):
                verify(text[: match.start() + split] + " " + text[match.start() + split :], 1)
                if budget <= 0:
                    break
            if budget <= 0:
                break
    ranked = sorted(
        verified.values(), key=lambda item: (item[1], -item[0]["matched_count"], item[0]["text"])
    )
    return [item[0] for item in ranked[:limit]]


def router(es, metadata, build_query):
    """Register the optional read-only spelling endpoint."""
    api = APIRouter(prefix="/api")

    @api.get("/spellcheck")
    def spellcheck(
        q: str = Query(default="", max_length=200),
        field: FIELDS = "all",
        mode: Literal["keyword", "hybrid", "semantic"] = "keyword",
        year_from: int | None = Query(default=None, ge=1, le=9999),
        year_to: int | None = Query(default=None, ge=1, le=9999),
        limit: int = Query(default=3, ge=1, le=3),
    ):
        if year_from is not None and year_to is not None and year_from > year_to:
            raise HTTPException(
                400, detail={"code": "invalid_parameter", "message": "年份范围无效", "details": {}}
            )
        if mode == "semantic":
            return {"query": q, "suggestions": []}
        generation, _ = metadata()
        return {
            "query": q,
            "suggestions": corrections(
                es, generation, q, field, year_from, year_to, limit, build_query
            ),
        }

    return api
