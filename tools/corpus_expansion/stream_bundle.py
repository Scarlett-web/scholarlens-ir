"""Import an offline-verified corpus bundle with bounded memory into NEW aliases.

No production configuration, existing aliases or original PDFs are changed.
Every acknowledged batch is read back before checkpointing; reruns are idempotent.
"""

import argparse
import gzip
import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
from filelock import FileLock

from backend.chunks import CHUNK_VERSION
from backend.embeddings import DIMENSIONS, MODEL, REVISION
from backend.mapping import index_definition
from backend.vector_index import atomic_state


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def lines(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            yield json.loads(line)


def vector_mapping(identity):
    properties = {
        key: {"type": "keyword"} for key in ("chunk_id", "paper_id", "field", "locator")
    }
    properties.update({key: {"type": "text"} for key in ("title", "text")})
    properties.update(
        {key: {"type": "integer"} for key in ("offset_start", "offset_end", "year")}
    )
    properties["embedding"] = {"type": "dense_vector", "dims": 384, "index": False}
    return {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "refresh_interval": "-1",
        },
        "mappings": {"dynamic": "strict", "_meta": identity, "properties": properties},
    }


def checked_bulk(es, generation, batch, key):
    bulk(
        es,
        ({"_index": generation, "_id": doc[key], "_source": doc} for doc in batch),
        chunk_size=32,
        max_chunk_bytes=4 * 1024 * 1024,
        max_retries=2,
    )
    stored = es.mget(index=generation, ids=[doc[key] for doc in batch])["docs"]
    for expected, actual in zip(batch, stored, strict=True):
        if not actual.get("found"):
            raise ValueError("missing read-back record")
        received = actual["_source"]
        if key == "chunk_id":
            expected_vector = expected.pop("embedding")
            received_vector = received.pop("embedding")
            array = np.asarray(received_vector)
            if (
                array.shape != (384,)
                or not np.isfinite(array).all()
                or abs(np.linalg.norm(array) - 1) > 1e-4
            ):
                raise ValueError("invalid read-back vector")
            if not np.allclose(array, expected_vector, atol=1e-7, rtol=1e-6):
                raise ValueError("read-back vector differs")
        if received != expected:
            raise ValueError("read-back source differs")


def run(args):
    root = args.bundle.resolve(strict=True)
    ready = json.loads((root / "offline-state.json").read_text())
    identity = ready["identity"]
    if any(
        identity.get(key) != expected
        for key, expected in {
            "model": MODEL,
            "model_revision": REVISION,
            "dimensions": DIMENSIONS,
            "chunk_version": CHUNK_VERSION,
        }.items()
    ):
        raise ValueError("unsupported bundle model or chunk format")
    if (
        ready["status"] != "ready"
        or ready["completed"] != identity["chunks"]
        or identity["papers"] != 4000
    ):
        raise ValueError("bundle incomplete")
    for name in ("papers.jsonl.gz", "chunks.jsonl.gz", "metadata.json", "vectors.npy"):
        if digest(root / name) != ready["files"][name]:
            raise ValueError("bundle checksum differs: " + name)
    for alias in (args.keyword_alias, args.vector_alias):
        if not re.fullmatch(
            r"scholarlens-(?:papers|vectors)-expansion-[a-z0-9-]+-real", alias
        ):
            raise ValueError("only isolated expansion aliases accepted")
    if not args.vector_alias.startswith(
        "scholarlens-vectors-"
    ) or not args.keyword_alias.startswith("scholarlens-papers-"):
        raise ValueError("alias roles differ")
    with (
        FileLock(str(root / "import.lock"), timeout=0),
        Elasticsearch(args.url, request_timeout=60, max_retries=2) as es,
    ):
        info = es.info()
        if (
            info["cluster_name"] != "scholarlens-local"
            or info["version"]["number"] != "8.19.23"
        ):
            raise ValueError("unexpected cluster")
        state_path = root / "import-state.json"
        metadata = json.loads((root / "metadata.json").read_text())
        if (
            metadata["input_sha256"] != identity["input_sha256"]
            or metadata["accepted_records"] != 4000
            or metadata["data_status"] != "real"
        ):
            raise ValueError("bundle metadata differs from identity")
        if state_path.exists():
            state = json.loads(state_path.read_text())
            if state["identity"] != identity or state["aliases"] != [
                args.keyword_alias,
                args.vector_alias,
            ]:
                raise ValueError("import checkpoint differs")
        else:
            if any(
                es.indices.exists(index=name) or es.indices.exists_alias(name=name)
                for name in (args.keyword_alias, args.vector_alias)
            ):
                raise ValueError("new alias already exists")
            suffix = uuid.uuid4().hex[:12]
            state = {
                "identity": identity,
                "aliases": [args.keyword_alias, args.vector_alias],
                "keyword_generation": args.keyword_alias + "-" + suffix,
                "vector_generation": args.vector_alias + "-" + suffix,
                "papers_completed": 0,
                "chunks_completed": 0,
                "status": "building",
            }
            atomic_state(state_path, state)
        kg, vg = state["keyword_generation"], state["vector_generation"]
        vi = {key: value for key, value in identity.items() if key != "input_sha256"}
        vi["base_generation"] = kg
        if not es.indices.exists(index=kg):
            if state["papers_completed"]:
                raise ValueError("keyword checkpoint generation missing")
            es.indices.create(index=kg, **index_definition(metadata))
        if not es.indices.exists(index=vg):
            if state["chunks_completed"]:
                raise ValueError("vector checkpoint generation missing")
            es.indices.create(index=vg, **vector_mapping(vi))
        arrays = np.load(root / "vectors.npy", mmap_mode="r", allow_pickle=False)
        if arrays.shape != (identity["chunks"], 384) or arrays.dtype != np.float32:
            raise ValueError("vector shape/type differs")
        for kind, filename, key, generation, total in (
            ("papers", "papers.jsonl.gz", "paper_id", kg, identity["papers"]),
            ("chunks", "chunks.jsonl.gz", "chunk_id", vg, identity["chunks"]),
        ):
            checkpoint = kind + "_completed"
            batch, count = [], 0
            for offset, record in enumerate(lines(root / filename)):
                count += 1
                if offset < state[checkpoint]:
                    continue
                if kind == "chunks":
                    record["embedding"] = arrays[offset].tolist()
                batch.append(record)
                if len(batch) == 32:
                    checked_bulk(es, generation, batch, key)
                    state[checkpoint] = count
                    atomic_state(state_path, state)
                    batch = []
                    if count % 3200 == 0:
                        print(f"{kind}={count}/{total}", flush=True)
            if batch:
                checked_bulk(es, generation, batch, key)
                state[checkpoint] = count
                atomic_state(state_path, state)
            if count != total:
                raise ValueError("bundle line count differs")
            es.indices.put_settings(
                index=generation, settings={"refresh_interval": "1s"}
            )
            es.indices.refresh(index=generation)
            if es.count(index=generation)["count"] != total:
                raise ValueError("ES count differs")
        built_at = datetime.now(UTC).isoformat()
        es.indices.put_mapping(
            index=kg,
            body={
                "_meta": {
                    **index_definition(metadata)["mappings"]["_meta"],
                    "last_built_at": built_at,
                }
            },
        )
        es.indices.put_mapping(index=vg, body={"_meta": {**vi, "built_at": built_at}})
        # Publish this isolated pair atomically; no existing production alias is touched.
        for alias, generation in ((args.keyword_alias, kg), (args.vector_alias, vg)):
            if es.indices.exists_alias(name=alias) and list(
                es.indices.get_alias(name=alias)
            ) != [generation]:
                raise ValueError("alias moved independently")
        es.indices.update_aliases(
            actions=[
                {"add": {"index": kg, "alias": args.keyword_alias}},
                {"add": {"index": vg, "alias": args.vector_alias}},
            ]
        )
        state.update(status="ready", completed_at=built_at, readback_verified=True)
        atomic_state(state_path, state)
        print(json.dumps(state), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--url", default="http://127.0.0.1:19200")
    parser.add_argument(
        "--keyword-alias", default="scholarlens-papers-expansion-20261103-real"
    )
    parser.add_argument(
        "--vector-alias", default="scholarlens-vectors-expansion-20261103-real"
    )
    run(parser.parse_args())
