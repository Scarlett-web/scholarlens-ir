"""A corrupt/incomplete bundle or a production alias must never reach ES."""

import hashlib
import json
from argparse import Namespace

import numpy as np
import pytest

from backend.chunks import CHUNK_VERSION
from backend.embeddings import DIMENSIONS, MODEL, REVISION
from tools.corpus_expansion import stream_bundle


def test_stdlib_vector_reader_matches_numpy_and_rejects_other_layouts(tmp_path):
    path = tmp_path / "vectors.npy"
    expected = np.random.default_rng(17).normal(size=(3, DIMENSIONS)).astype("<f4")
    np.save(path, expected, allow_pickle=False)
    reader = stream_bundle.NpyVectors(path, 3)
    try:
        assert [reader[i] for i in range(3)] == expected.tolist()
        with pytest.raises(IndexError):
            reader[3]
    finally:
        reader.close()
    for incompatible in (
        expected.astype(">f4"),
        expected.astype("float64"),
        np.asfortranarray(expected),
        expected[:, :100],
    ):
        np.save(path, incompatible, allow_pickle=False)
        with pytest.raises(ValueError):
            stream_bundle.NpyVectors(path, 3)


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("preflight failure contacted Elasticsearch")

    monkeypatch.setattr(stream_bundle, "Elasticsearch", forbidden)
    state = {
        "status": "ready",
        "completed": 1,
        "identity": {
            "model": MODEL,
            "model_revision": REVISION,
            "dimensions": DIMENSIONS,
            "chunk_version": CHUNK_VERSION,
            "papers": 4000,
            "chunks": 1,
        },
        "files": {},
    }
    for name in ("papers.jsonl.gz", "chunks.jsonl.gz", "metadata.json", "vectors.npy"):
        (tmp_path / name).write_bytes(b"preflight-only; not real corpus data")
        state["files"][name] = hashlib.sha256(
            (tmp_path / name).read_bytes()
        ).hexdigest()
    args = Namespace(
        bundle=tmp_path,
        url="http://127.0.0.1:19200",
        keyword_alias="scholarlens-papers-expansion-test-real",
        vector_alias="scholarlens-vectors-expansion-test-real",
    )
    return args, state


@pytest.mark.parametrize(
    "change",
    ["incomplete", "wrong-model", "wrong-revision", "wrong-dimensions", "wrong-chunks"],
)
def test_incomplete_or_incompatible_bundle_stops_before_es(bundle, change):
    args, state = bundle
    if change == "incomplete":
        state["status"] = "building"
    else:
        key = {
            "wrong-model": "model",
            "wrong-revision": "model_revision",
            "wrong-dimensions": "dimensions",
            "wrong-chunks": "chunk_version",
        }[change]
        state["identity"][key] = "different"
    (args.bundle / "offline-state.json").write_text(json.dumps(state))
    with pytest.raises(ValueError):
        stream_bundle.run(args)


@pytest.mark.parametrize(
    "file", ["papers.jsonl.gz", "chunks.jsonl.gz", "metadata.json", "vectors.npy"]
)
def test_corrupt_transfer_stops_before_es(bundle, file):
    args, state = bundle
    (args.bundle / "offline-state.json").write_text(json.dumps(state))
    (args.bundle / file).write_bytes(b"corrupt transfer")
    with pytest.raises(ValueError, match="checksum"):
        stream_bundle.run(args)


@pytest.mark.parametrize("alias", ["keyword_alias", "vector_alias"])
def test_existing_production_alias_is_not_a_valid_target(bundle, alias):
    args, state = bundle
    setattr(
        args,
        alias,
        "scholarlens-desktop-real"
        if alias == "keyword_alias"
        else "scholarlens-vectors-desktop-real",
    )
    (args.bundle / "offline-state.json").write_text(json.dumps(state))
    with pytest.raises(ValueError, match="isolated"):
        stream_bundle.run(args)


@pytest.mark.parametrize("changed", ["cluster_name", "cluster_uuid", "version"])
def test_wrong_target_identity_cannot_create_an_index(bundle, monkeypatch, changed):
    args, state = bundle
    args.cluster_name, args.cluster_uuid = "expected-cluster", "expected-uuid"
    np.save(args.bundle / "vectors.npy", np.ones((1, DIMENSIONS), dtype="<f4"))
    state["files"]["vectors.npy"] = hashlib.sha256(
        (args.bundle / "vectors.npy").read_bytes()
    ).hexdigest()
    (args.bundle / "offline-state.json").write_text(json.dumps(state))
    identity = {
        "cluster_name": args.cluster_name,
        "cluster_uuid": args.cluster_uuid,
        "version": {"number": "8.19.23"},
    }
    identity[changed] = {"number": "different"} if changed == "version" else "different"

    class ReadOnlyTarget:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def info(self):
            return identity

    monkeypatch.setattr(stream_bundle, "Elasticsearch", ReadOnlyTarget)
    with pytest.raises(ValueError, match="unexpected cluster"):
        stream_bundle.run(args)
