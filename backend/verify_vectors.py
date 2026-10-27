"""Read-only full vector/source audit, including every stored embedding and locator."""

import argparse
import hashlib
import json
from pathlib import Path
import time

from elasticsearch.helpers import scan
import numpy as np

from backend.chunks import chunks
from backend.config import Settings, make_client
from backend.retrieval import vector_metadata


def verify(settings, output: Path):
    if output.exists():
        raise FileExistsError("choose a new verification report path")
    start = time.monotonic()
    with make_client(settings) as es:
        base = next(iter(es.indices.get_mapping(index=settings.index)))
        generation, meta = vector_metadata(es, settings, base)
        docs = sorted((h["_source"] for h in scan(es, index=base)), key=lambda d: d["paper_id"])
        expected_list = [c for d in docs for c in chunks(d)]
        fingerprint = hashlib.sha256(json.dumps(expected_list, sort_keys=True).encode()).hexdigest()
        assert fingerprint == meta["fingerprint"]
        expected = {c["chunk_id"]: c for c in expected_list}
        assert len(expected) == meta["chunks"]
        seen = set()
        papers = set()
        fields = {}
        min_norm = 2.0
        max_norm = 0.0
        for hit in scan(es, index=generation, size=100, scroll="5m"):
            value = hit["_source"]
            vector = np.asarray(value.pop("embedding"), dtype=np.float32)
            assert vector.shape == (384,) and np.isfinite(vector).all()
            norm = float(np.linalg.norm(vector))
            assert abs(norm - 1) < 1e-4
            min_norm = min(min_norm, norm)
            max_norm = max(max_norm, norm)
            assert value == expected[hit["_id"]] and hit["_id"] == value["chunk_id"]
            assert hit["_id"] not in seen
            seen.add(hit["_id"])
            papers.add(value["paper_id"])
            fields[value["field"]] = fields.get(value["field"], 0) + 1
        assert seen == set(expected) and len(papers) == len(docs)
        report = {
            "status": "verified",
            "base_generation": base,
            "vector_generation": generation,
            "papers": len(papers),
            "chunks": len(seen),
            "all_sources_and_locators_exact": True,
            "all_embeddings_finite_normalized_and_384d": True,
            "min_norm": min_norm,
            "max_norm": max_norm,
            "chunk_fields": fields,
            "input_fingerprint": fingerprint,
            "model": meta["model"],
            "model_revision": meta["model_revision"],
            "elapsed_seconds": round(time.monotonic() - start, 3),
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=Path("backend/.runtime/v2-vector-verification.json")
    )
    print(json.dumps(verify(Settings.from_env(), parser.parse_args().output), indent=2))
