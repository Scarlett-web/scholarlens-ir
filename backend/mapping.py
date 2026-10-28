"""Versioned single-shard mapping; all six searchable fields use explicit BM25."""

from backend.schema import SEARCH_FIELDS

MAPPING_VERSION = "papers-v2-cjk"


def index_definition(metadata: dict) -> dict:
    """Build a new generation's settings/mapping with its import evidence."""
    properties = {
        field: {"type": "text", "analyzer": "standard", "similarity": "paper_bm25",
                "fields": {"cjk": {"type": "text", "analyzer": "cjk", "similarity": "paper_bm25"}}}
        for field in (*SEARCH_FIELDS, "abstract")
    }
    properties.update(
        {
            "paper_id": {"type": "keyword"},
            "year": {"type": "integer"},
            "date_value": {"type": "date", "format": "strict_date"},
            "pages": {
                "properties": {key: {"type": "integer"} for key in ("first", "last", "count")}
            },
            "pdf_path": {"type": "keyword", "index": False, "doc_values": False},
            "source_file": {"type": "keyword", "index": False, "doc_values": False},
            "parse_status": {"type": "keyword"},
            "errors": {"type": "keyword", "index": False, "doc_values": False},
        }
    )
    return {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "similarity": {"paper_bm25": {"type": "BM25", "k1": 1.2, "b": 0.75}},
        },
        "mappings": {
            "dynamic": "strict",
            "_meta": {"mapping_version": MAPPING_VERSION, **metadata},
            "properties": properties,
        },
    }
