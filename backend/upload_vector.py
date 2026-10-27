"""Build an independent vector generation for approved/indexed uploads."""

from datetime import datetime, timezone
import hashlib
import json
import uuid
from pathlib import Path
from filelock import FileLock

from elasticsearch.helpers import bulk, scan

from backend.chunks import CHUNK_VERSION, chunks
from backend.config import Settings, make_client
from backend.embeddings import DIMENSIONS, MODEL, REVISION, Encoder


def vectorize_uploads(settings: Settings) -> dict:
    root = Path(settings.runtime_dir)
    root.mkdir(parents=True, exist_ok=True)
    if not settings.upload_vector_index.startswith("scholarlens-vectors-uploads-"):
        raise ValueError("invalid upload vector alias")
    with FileLock(str(root / (settings.upload_vector_index + ".lock")), timeout=0):
        return _vectorize_uploads(settings)


def _vectorize_uploads(settings: Settings) -> dict:
    """Rebuild only the isolated upload vector alias; base vectors remain untouched."""
    if not settings.upload_vector_index.startswith("scholarlens-vectors-uploads-"):
        raise ValueError("upload vectors require a dedicated alias")
    es = make_client(settings)
    try:
        if not es.indices.exists_alias(name=settings.uploads_index):
            return {"status": "no_uploads", "chunks": 0}
        base = next(iter(es.indices.get_alias(name=settings.uploads_index)))
        docs = [h["_source"] for h in scan(es, index=base)]
        all_chunks = [c for doc in docs for c in chunks(doc)]
        generation = settings.upload_vector_index + "-" + uuid.uuid4().hex[:12]
        meta = {
            "base_generation": base,
            "model": MODEL,
            "model_revision": REVISION,
            "chunk_version": CHUNK_VERSION,
            "dimensions": DIMENSIONS,
            "papers": len(docs),
            "chunks": len(all_chunks),
            "input_fingerprint": hashlib.sha256(
                json.dumps(all_chunks, sort_keys=True).encode()
            ).hexdigest(),
            "built_at": datetime.now(timezone.utc).isoformat(),
        }
        mapping = {
            "dynamic": "strict",
            "_meta": meta,
            "properties": {
                "chunk_id": {"type": "keyword"},
                "paper_id": {"type": "keyword"},
                "title": {"type": "text"},
                "field": {"type": "keyword"},
                "offset_start": {"type": "integer"},
                "offset_end": {"type": "integer"},
                "locator": {"type": "keyword"},
                "text": {"type": "text"},
                "year": {"type": "integer"},
                "embedding": {"type": "dense_vector", "dims": DIMENSIONS, "index": False},
            },
        }
        es.indices.create(
            index=generation,
            settings={"number_of_shards": 1, "number_of_replicas": 0, "refresh_interval": "-1"},
            mappings=mapping,
        )
        previous = (
            list(es.indices.get_alias(name=settings.upload_vector_index))
            if es.indices.exists_alias(name=settings.upload_vector_index)
            else []
        )
        reusable = None
        if len(previous) == 1:
            old_meta = es.indices.get_mapping(index=previous[0])[previous[0]]["mappings"].get(
                "_meta", {}
            )
            if (
                old_meta.get("model_revision") == REVISION
                and old_meta.get("chunk_version") == CHUNK_VERSION
            ):
                reusable = previous[0]
        encoder = None
        reused = 0
        embedded = 0
        for offset in range(0, len(all_chunks), 8):
            batch = all_chunks[offset : offset + 8]
            old = {}
            if reusable:
                old = {
                    d["_id"]: d["_source"]
                    for d in es.mget(index=reusable, ids=[c["chunk_id"] for c in batch])["docs"]
                    if d.get("found")
                }
            available = {
                c["chunk_id"]: old[c["chunk_id"]]["embedding"]
                for c in batch
                if c["chunk_id"] in old
                and {k: v for k, v in old[c["chunk_id"]].items() if k != "embedding"} == c
            }
            missing = [c for c in batch if c["chunk_id"] not in available]
            if missing:
                encoder = encoder or Encoder(settings.model_dir)
                available.update(
                    {
                        c["chunk_id"]: v
                        for c, v in zip(
                            missing,
                            encoder.encode([" ".join(c["text"].split()) for c in missing]),
                            strict=True,
                        )
                    }
                )
            reused += len(batch) - len(missing)
            embedded += len(missing)
            vectors = [available[c["chunk_id"]] for c in batch]
            bulk(
                es.options(request_timeout=60),
                [
                    {"_index": generation, "_id": c["chunk_id"], "_source": {**c, "embedding": v}}
                    for c, v in zip(batch, vectors, strict=True)
                ],
            )
        es.indices.refresh(index=generation)
        es.indices.put_settings(index=generation, settings={"refresh_interval": "1s"})
        actual = es.count(index=generation)["count"]
        if actual != len(all_chunks):
            raise ValueError("upload vector count mismatch")
        # Refuse publication if the source changed while embeddings were generated.
        if list(es.indices.get_alias(name=settings.uploads_index)) != [base]:
            raise ValueError("upload source generation changed; old vector alias preserved")
        actions = [
            {"remove": {"index": old, "alias": settings.upload_vector_index}} for old in previous
        ]
        actions.append({"add": {"index": generation, "alias": settings.upload_vector_index}})
        es.indices.update_aliases(actions=actions)
        return {
            "status": "ready",
            "generation": generation,
            "previous_generations": previous,
            "papers": len(docs),
            "chunks": actual,
            "reused_chunks": reused,
            "embedded_chunks": embedded,
            "built_at": meta["built_at"],
        }
    finally:
        es.close()
