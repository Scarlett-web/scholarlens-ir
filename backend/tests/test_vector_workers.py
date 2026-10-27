"""Parallel embedding preserves acknowledgment checkpoints and serial model output."""
from dataclasses import replace
import json
import uuid

import numpy as np
import pytest
from backend.import_jsonl import import_records,load_jsonl
from backend.embeddings import Encoder
from backend.chunks import chunks
import backend.vector_index as module
from test_v2 import env,REAL_ID


def test_parallel_resume_and_equivalent_embeddings(env,tmp_path,monkeypatch):
    _,es,settings,_=env
    row=es.get(index=settings.index,id=REAL_ID)["_source"]
    row.pop("date_value",None)
    row["fulltext"]=row.get("fulltext","")[:3500]
    row["abstract"]=row.get("abstract","")[:500]
    source=tmp_path/"selected.jsonl"
    source.write_text(json.dumps(row)+"\n",encoding="utf-8")
    docs,meta=load_jsonl(source,"real")
    alias="scholarlens-workers-"+uuid.uuid4().hex[:8]+"-real"
    import_records(es,alias,docs,meta)
    config=replace(settings,index=alias,vector_index="scholarlens-vectors-workers-"+uuid.uuid4().hex[:8])
    checkpoint=tmp_path/"parallel.json"
    original=module.bulk
    def fail_after_ack(*args,**kwargs):
        original(*args,**kwargs)
        raise RuntimeError("controlled failure after acknowledged write")
    monkeypatch.setattr(module,"bulk",fail_after_ack)
    monkeypatch.setattr(module.time,"sleep",lambda _:None)
    with pytest.raises(RuntimeError):module.build(config,checkpoint,batch_size=1,workers=2)
    assert json.loads(checkpoint.read_text())["completed"]==0
    assert not es.indices.exists_alias(name=config.vector_index)
    monkeypatch.setattr(module,"bulk",original)
    result=module.build(config,checkpoint,batch_size=1,workers=4)
    assert result["status"]=="ready"
    assert es.count(index=config.vector_index)["count"]==result["identity"]["chunks"]
    expected_chunks=chunks(row)
    expected=Encoder(settings.model_dir).encode([" ".join(c["text"].split()) for c in expected_chunks])
    for item,vector in zip(expected_chunks,expected,strict=True):
        stored=es.get(index=config.vector_index,id=item["chunk_id"])["_source"]
        assert stored["text"]==item["text"]
        assert float(np.dot(vector,stored["embedding"]))>0.99999
    assert module.build(config,checkpoint,workers=2)==result
    assert es.count(index=settings.index)["count"]==859
