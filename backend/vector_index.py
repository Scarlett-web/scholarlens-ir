"""Resumable independent vector generation; publish only a fully verified build."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import uuid
import re

from elasticsearch.helpers import bulk, scan
from filelock import FileLock

from backend.chunks import CHUNK_VERSION, chunks
from backend.config import Settings, make_client
from backend.embeddings import DIMENSIONS, MODEL, REVISION, Encoder


def atomic_state(path: Path, state: dict):
    """Windows readers/AV can briefly deny replace; retain the previous checkpoint."""
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    for attempt in range(10):
        try:
            temp.replace(path)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.05 * (attempt + 1))


def build(settings: Settings, state_path: Path, batch_size: int = 8) -> dict:
    """Acquire a process lock before reading or modifying a checkpoint."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    if not re.fullmatch(
        r"scholarlens-vectors-[a-z0-9-]+", settings.vector_index
    ) or settings.vector_index in (settings.index, settings.uploads_index):
        raise ValueError("vector publication requires a separate scholarlens-vectors-* alias")
    runtime = Path(settings.runtime_dir)
    runtime.mkdir(parents=True, exist_ok=True)
    with FileLock(str(runtime / (settings.vector_index + ".build.lock")), timeout=0):
        with FileLock(str(state_path) + ".lock", timeout=0):
            return _build(settings, state_path, batch_size)


def _build(settings: Settings, state_path: Path, batch_size: int = 8) -> dict:
    """Read base ES only, checkpoint acknowledged batches; retain failed generations."""
    if not settings.vector_index.startswith("scholarlens-vectors-") or settings.vector_index in (
        settings.index,
        settings.uploads_index,
    ):
        raise ValueError("vector publication requires a separate scholarlens-vectors-* alias")
    es = make_client(settings)
    try:
        mappings = es.indices.get_mapping(index=settings.index)
        if len(mappings) != 1:
            raise ValueError("base alias must identify one generation")
        base = next(iter(mappings))
        docs = sorted((h["_source"] for h in scan(es, index=base)), key=lambda d: d["paper_id"])
        all_chunks = [c for d in docs for c in chunks(d)]
        fingerprint = hashlib.sha256(json.dumps(all_chunks, sort_keys=True).encode()).hexdigest()
        identity = {
            "base_generation": base,
            "model": MODEL,
            "model_revision": REVISION,
            "chunk_version": CHUNK_VERSION,
            "fingerprint": fingerprint,
            "dimensions": DIMENSIONS,
            "papers": len(docs),
            "chunks": len(all_chunks),
        }
        if state_path.exists():
            state = json.loads(state_path.read_text())
            if state["identity"] != identity:
                raise ValueError(
                    "checkpoint belongs to a different input/model; choose new state path"
                )
        else:
            generation = settings.vector_index + "-" + uuid.uuid4().hex[:12]
            mapping = {
                "dynamic": "strict",
                "_meta": identity,
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
            state = {
                "identity": identity,
                "generation": generation,
                "completed": 0,
                "status": "building",
            }
        generation = state["generation"]
        if not generation.startswith(settings.vector_index + "-"):
            raise ValueError("checkpoint generation belongs to a different vector alias")
        state["alias"] = settings.vector_index
        if state["status"] == "ready":
            if es.count(index=generation)["count"] != len(all_chunks):
                raise ValueError("published generation count mismatch")
            if list(es.indices.get_alias(name=settings.vector_index)) != [generation]:
                raise ValueError("published alias changed independently; inspect before resuming")
            published_meta = es.indices.get_mapping(index=generation)[generation]["mappings"][
                "_meta"
            ]
            if "built_at" not in published_meta:
                es.indices.put_mapping(
                    index=generation,
                    body={"_meta": {**published_meta, "built_at": state["completed_at"]}},
                )
            return state
        encoder = Encoder(settings.model_dir)
        state_path.parent.mkdir(parents=True, exist_ok=True)

        def save():
            atomic_state(state_path, state)

        save()
        started = time.monotonic()
        for offset in range(state["completed"], len(all_chunks), batch_size):
            batch = all_chunks[offset : offset + batch_size]
            for attempt in range(3):
                try:
                    vectors = encoder.encode([" ".join(c["text"].split()) for c in batch])
                    bulk(
                        es.options(request_timeout=60),
                        [
                            {
                                "_index": generation,
                                "_id": c["chunk_id"],
                                "_source": {**c, "embedding": v},
                            }
                            for c, v in zip(batch, vectors, strict=True)
                        ],
                    )
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    time.sleep(attempt + 1)
            state["completed"] = offset + len(batch)
            save()
            if state["completed"] % (batch_size * 100) == 0:
                print(
                    f"chunks={state['completed']}/{len(all_chunks)} elapsed={time.monotonic() - started:.1f}s",
                    flush=True,
                )
        es.indices.put_settings(index=generation, settings={"refresh_interval": "1s"})
        es.indices.refresh(index=generation)
        if es.count(index=generation)["count"] != len(all_chunks):
            raise ValueError("chunk count mismatch")
        # Publication is separate from the protected BM25 alias.
        previous = (
            list(es.indices.get_alias(name=settings.vector_index))
            if es.indices.exists_alias(name=settings.vector_index)
            else []
        )
        if previous == [generation]:
            previous = state.get("previous_generations", [])
        else:
            state["previous_generations"] = previous
            save()
        completed_at = state.get("completed_at") or datetime.now(timezone.utc).isoformat()
        es.indices.put_mapping(
            index=generation, body={"_meta": {**identity, "built_at": completed_at}}
        )
        es.indices.update_aliases(
            actions=[
                *(
                    {"remove": {"index": old, "alias": settings.vector_index}}
                    for old in previous
                    if old != generation
                ),
                {"add": {"index": generation, "alias": settings.vector_index}},
            ]
        )
        state.update(
            status="ready",
            previous_generations=previous,
            completed_at=completed_at,
        )
        save()
        return state
    finally:
        es.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", default="backend/.runtime/vector-build.json")
    parser.add_argument("--batch-size", type=int, choices=range(1, 33), default=8)
    args = parser.parse_args()
    print(json.dumps(build(Settings.from_env(), Path(args.state), args.batch_size), indent=2))
