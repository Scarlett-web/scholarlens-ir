"""Pinned MiniLM ONNX CPU inference; no model download in HTTP requests."""

import hashlib
import json
from pathlib import Path
import threading
import time

import httpx

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
DIMENSIONS = 384
FILES = {
    "onnx/model.onnx": (
        "model.onnx",
        90405214,
        "6fd5d72fe4589f189f8ebc006442dbb529bb7ce38f8082112682524616046452",
    ),
    "tokenizer.json": (
        "tokenizer.json",
        466247,
        "be50c3628f2bf5bb5e3a7f17b1f74611b2561a3a27eeab05e5aa30f411572037",
    ),
    "1_Pooling/config.json": (
        "pooling.json",
        190,
        "4be450dde3b0273bb9787637cfbd28fe04a7ba6ab9d36ac48e92b11e350ffc23",
    ),
    "sentence_bert_config.json": (
        "sentence_bert_config.json",
        53,
        "fc1993fde0a95c24ec6c022539d41cf6e2f7c9721e5415d6fb6897472a9cd4b7",
    ),
}


def download_model(root: Path) -> dict:
    """Download <91 MB pinned assets, verify sizes/SHA, atomically install each file."""
    root.mkdir(parents=True, exist_ok=True)
    manifest = {"model": MODEL, "revision": REVISION, "dimensions": DIMENSIONS, "files": {}}
    for remote, (name, size, expected) in FILES.items():
        dest = root / name
        if not dest.exists():
            part = root / (name + ".partial")
            for attempt in range(3):
                try:
                    with httpx.stream(
                        "GET",
                        f"https://huggingface.co/{MODEL}/resolve/{REVISION}/{remote}",
                        follow_redirects=True,
                        timeout=60,
                    ) as r:
                        r.raise_for_status()
                        with part.open("wb") as f:
                            total = 0
                            for block in r.iter_bytes(1024 * 1024):
                                total += len(block)
                                if total > size:
                                    raise ValueError("model asset exceeds expected size")
                                f.write(block)
                    if part.stat().st_size != size:
                        raise ValueError("model size mismatch")
                    if expected and hashlib.sha256(part.read_bytes()).hexdigest() != expected:
                        raise ValueError("model SHA256 mismatch")
                    part.replace(dest)
                    break
                except (httpx.HTTPError, ValueError):
                    if attempt == 2:
                        raise
                    time.sleep(attempt + 1)
        digest = hashlib.sha256(dest.read_bytes()).hexdigest()
        if dest.stat().st_size != size or (expected and digest != expected):
            raise ValueError("local model asset mismatch")
        manifest["files"][name] = {"sha256": digest, "bytes": size}
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


class Encoder:
    """One shared bounded CPU session with mean pooling and L2 normalization."""

    def __init__(self, root: str):
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer

        path = Path(root)
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        if manifest["revision"] != REVISION or manifest["dimensions"] != DIMENSIONS:
            raise ValueError("unsupported model manifest")
        expected_assets = {name: expected for name, _, expected in FILES.values()}
        if set(manifest["files"]) != set(expected_assets):
            raise ValueError("incomplete model manifest")
        for name, info in manifest["files"].items():
            if (
                info["sha256"] != expected_assets[name]
                or hashlib.sha256((path / name).read_bytes()).hexdigest() != info["sha256"]
            ):
                raise ValueError("model checksum mismatch")
        self.np = np
        self.tokenizer = Tokenizer.from_file(str(path / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=256)
        self.tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(
            str(path / "model.onnx"), options, providers=["CPUExecutionProvider"]
        )
        self.lock = threading.Lock()

    def encode(self, texts: list[str]) -> list[list[float]]:
        """Encode a small nonempty batch; reject zero/nonfinite vectors."""
        np = self.np
        if not texts:
            return []
        with self.lock:
            tokens = self.tokenizer.encode_batch(texts)
            masks = np.asarray([t.attention_mask for t in tokens], dtype=np.int64)
            inputs = {
                "input_ids": np.asarray([t.ids for t in tokens], dtype=np.int64),
                "attention_mask": masks,
                "token_type_ids": np.asarray([t.type_ids for t in tokens], dtype=np.int64),
            }
            inputs = {i.name: inputs[i.name] for i in self.session.get_inputs()}
            hidden = self.session.run(None, inputs)[0]
            vectors = (hidden * masks[:, :, None]).sum(1) / np.maximum(masks.sum(1)[:, None], 1)
            vectors /= np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
        if vectors.shape != (len(texts), DIMENSIONS) or not np.isfinite(vectors).all():
            raise ValueError("invalid embedding dimensions/values")
        if not (np.linalg.norm(vectors, axis=1) > 0.99).all():
            raise ValueError("zero vector")
        return vectors.astype(np.float32).tolist()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(Path(__file__).parent / ".runtime/minilm"))
    print(json.dumps(download_model(Path(parser.parse_args().output)), indent=2))
