"""New CJK generations and legacy mappings, using only uniquely owned indexes."""
import copy
import json
import uuid

from elasticsearch import Elasticsearch
from fastapi.testclient import TestClient
import pytest

from backend.app1 import create_app
from backend.config import Settings
from backend.import_jsonl import import_records, load_jsonl
from backend.mapping import index_definition
import backend.import_jsonl as importer

pytestmark = pytest.mark.integration


@pytest.fixture(params=['cjk', 'legacy'])
def chinese_library(tmp_path, monkeypatch, request):
    es=Elasticsearch('http://127.0.0.1:9200')
    alias='scholarlens-chinese-test-'+uuid.uuid4().hex[:12]+'-mock'
    path=tmp_path/'chinese.jsonl'
    path.write_text(json.dumps({'paper_id':'mock-cn', 'title':'中文磁共振 MRI 成像研究',
        'authors':['张三'], 'date':'2024-03-12','year':2024,
        'affiliation':['北京大学'], 'address':['北京市海淀区'],
        'abstract':'神经成像研究', 'fulltext':'磁共振成像 MRI 用于脑结构分析。神经科学研究方法。'},ensure_ascii=False),encoding='utf-8')
    if request.param=='legacy':
        def legacy(meta):
            definition=copy.deepcopy(index_definition(meta))
            for field in definition['mappings']['properties'].values():
                field.pop('fields',None)
            return definition
        monkeypatch.setattr(importer,'index_definition',legacy)
    records,metadata=load_jsonl(path,'mock')
    try:
        result=import_records(es,alias,records,metadata)
        with TestClient(create_app(Settings(index=alias,runtime_dir=str(tmp_path/'runtime'),
                   uploads_index='scholarlens-uploads-chinese-test-'+uuid.uuid4().hex[:12]+'-real'),es)) as api:
            yield api,es,result,request.param
    finally:
        for name in es.indices.get(index=alias+'-*',allow_no_indices=True):
            assert name.startswith(alias+'-')
            es.indices.delete(index=name)
        es.close()


def test_chinese_and_mixed_queries_with_six_real_highlight_fields(chinese_library):
    api,es,result,kind=chinese_library
    for field,query in [('title','磁共振'),('authors','张三'),('date','2024-03'),
                        ('affiliation','北京大学'),('address','海淀区'),('fulltext','脑结构')]:
        response=api.get('/api/search',params={'q':query,'field':field})
        assert response.status_code==200,response.text
        body=response.json();assert body['total']==1,body
        row=body['results'][0]
        assert field in row['matched_fields'] and '<em>' in str(row['highlights'][field])
        assert row['date']=='2024-03-12' and row['affiliation']==['北京大学'] and row['address']==['北京市海淀区']
        assert not any(key.endswith('.cjk') for key in row['highlights'])
    mixed=api.get('/api/search',params={'q':'磁共振 MRI','field':'all'})
    assert mixed.status_code==200 and mixed.json()['total']==1
    if kind=='cjk':
        tokens=es.indices.analyze(index=result['generation'],analyzer='cjk',text='磁共振成像')
        assert any(len(token['token'])==2 for token in tokens['tokens'])


def test_explicit_chinese_phrase_is_not_broadened(chinese_library):
    api,*_=chinese_library
    result=api.get('/api/search',params={'q':'磁共振成像','field':'fulltext','phrase':True})
    assert result.status_code==200 and result.json()['total']==1
    missing=api.get('/api/search',params={'q':'不存在的中文短语','phrase':True})
    assert missing.status_code==200 and missing.json()['total']==0
