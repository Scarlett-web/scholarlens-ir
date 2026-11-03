"""Prepare text-only corpus and resumable local embeddings; never touches live ES.

Run from the repository root with --input, --output and --model-dir.
Original JSONL is immutable. PDF delivery is deliberately a separate acceptance gate.
"""

import argparse
import gzip
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from filelock import FileLock

from backend.chunks import CHUNK_VERSION, chunks
from backend.embeddings import DIMENSIONS, MODEL, REVISION
from backend.import_jsonl import load_jsonl
from backend.vector_index import atomic_state, encoded_batches


def enable_directml(model_dir):
    """Optional isolated Windows acceleration; verify against the pinned CPU model."""
    import onnxruntime as ort

    import backend.vector_index as builder
    from backend.embeddings import Encoder

    if "DmlExecutionProvider" not in ort.get_available_providers():
        raise ValueError(
            "DirectML runtime is not installed; use CPU or an isolated runtime"
        )

    class AcceleratedEncoder(Encoder):
        def __init__(self, root):
            super().__init__(root)
            probes = ["Academic retrieval and source evidence.", "磁共振成像研究 MRI"]
            expected = np.asarray(self.encode(probes))
            options = ort.SessionOptions()
            options.enable_mem_pattern = False
            options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            self.session = ort.InferenceSession(
                str(Path(root) / "model.onnx"),
                options,
                providers=["DmlExecutionProvider", "CPUExecutionProvider"],
            )
            actual = np.asarray(self.encode(probes))
            if not ((expected * actual).sum(axis=1) > 0.99999).all():
                raise ValueError("accelerated output differs from pinned CPU reference")

    builder.Encoder = AcceleratedEncoder


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_lines(path, records):
    temp = path.with_suffix(".partial")
    with gzip.open(temp, "wt", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    temp.replace(path)


def run(args):
    if args.provider == "directml":
        if args.workers != 1:
            raise ValueError("DirectML requires one encoder to bound GPU memory")
        enable_directml(args.model_dir)
    args.output.mkdir(parents=True, exist_ok=True)
    with FileLock(str(args.output / "offline.lock"), timeout=0):
        docs, metadata = load_jsonl(args.input, "real")
        if len(docs) != args.expected_papers:
            raise ValueError("unexpected paper count")
        docs.sort(key=lambda doc: doc["paper_id"])
        items = [item for doc in docs for item in chunks(doc)]
        identity = {
            "model": MODEL,
            "model_revision": REVISION,
            "dimensions": DIMENSIONS,
            "chunk_version": CHUNK_VERSION,
            "papers": len(docs),
            "chunks": len(items),
            "fingerprint": hashlib.sha256(
                json.dumps(items, sort_keys=True).encode()
            ).hexdigest(),
            "input_sha256": metadata["input_sha256"],
        }
        state_path = args.output / "offline-state.json"
        if state_path.exists():
            state = json.loads(state_path.read_text())
            if state["identity"] != identity:
                raise ValueError("checkpoint input/model differs")
        else:
            write_lines(args.output / "papers.jsonl.gz", docs)
            write_lines(args.output / "chunks.jsonl.gz", items)
            atomic_state(args.output / "metadata.json", metadata)
            state = {"identity": identity, "completed": 0, "status": "building"}
            atomic_state(state_path, state)
        path = args.output / "vectors.npy"
        if not path.exists() and state["completed"]:
            raise ValueError("checkpoint vectors missing")
        vectors = np.lib.format.open_memmap(
            path,
            mode="r+" if path.exists() else "w+",
            dtype=np.float32,
            shape=(len(items), DIMENSIONS),
        )
        if vectors.shape != (len(items), DIMENSIONS) or vectors.dtype != np.float32:
            raise ValueError("vector file shape/type differs")
        started = time.monotonic()
        for offset, batch, values in encoded_batches(
            items, state["completed"], 32, str(args.model_dir), args.workers
        ):
            vectors[offset : offset + len(batch)] = values
            vectors.flush()
            state["completed"] = offset + len(batch)
            atomic_state(state_path, state)
            if state["completed"] % 3200 == 0:
                print(
                    f"chunks={state['completed']}/{len(items)} elapsed={time.monotonic() - started:.1f}s",
                    flush=True,
                )
        for start in range(0, len(items), 1024):
            batch = vectors[start : start + 1024]
            if not np.isfinite(batch).all() or not np.allclose(
                np.linalg.norm(batch, axis=1), 1, atol=1e-4
            ):
                raise ValueError("invalid vector norm/values")
        state.update(
            status="ready",
            files={
                name: sha(args.output / name)
                for name in (
                    "papers.jsonl.gz",
                    "chunks.jsonl.gz",
                    "metadata.json",
                    "vectors.npy",
                )
            },
        )
        atomic_state(state_path, state)
        print(json.dumps(state), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--expected-papers", type=int, default=4000)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    parser.add_argument("--provider", choices=("cpu", "directml"), default="cpu")
    run(parser.parse_args())
