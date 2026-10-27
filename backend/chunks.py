"""Stable character-located chunks; offsets refer exactly to indexed source fields."""

import hashlib
import re

CHUNK_VERSION = "chars900-overlap100-v1"


def chunks(doc: dict, size: int = 900, overlap: int = 100) -> list[dict]:
    """Return title, abstract and safe body chunks, retaining exact quotes/offsets."""
    result = []
    for field in ("title", "abstract", "fulltext"):
        text = doc.get(field, "")
        if field == "fulltext" and (
            "\ufffd" in text or "unreadable_characters_in_fulltext" in doc.get("errors", [])
        ):
            continue
        start = 0
        while start < len(text):
            end = min(len(text), start + size)
            if end < len(text):
                matches = list(re.finditer(r"\s+", text[start + size // 2 : end]))
                if matches:
                    end = start + size // 2 + matches[-1].start()
            quote = text[start:end]
            if quote.strip():
                key = f"{CHUNK_VERSION}\0{doc['paper_id']}\0{field}\0{start}\0{end}\0{quote}"
                result.append(
                    {
                        "chunk_id": "chunk:" + hashlib.sha256(key.encode()).hexdigest(),
                        "paper_id": doc["paper_id"],
                        "title": doc.get("title", ""),
                        "field": field,
                        "offset_start": start,
                        "offset_end": end,
                        "locator": f"{field}:chars:{start}-{end}",
                        "text": quote,
                        "year": doc.get("year"),
                    }
                )
            if end == len(text):
                break
            start = max(start + 1, end - overlap)
    return result
