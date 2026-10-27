"""Ephemeral English Porter analyzer comparison; formal mappings are never modified."""

import argparse
import json
import uuid

from elasticsearch import Elasticsearch


def compare(url: str = "http://127.0.0.1:9200") -> dict:
    client = Elasticsearch(url)
    index = "scholarlens-porter-test-" + uuid.uuid4().hex[:10]
    try:
        client.indices.create(
            index=index,
            settings={
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "analysis": {
                    "analyzer": {
                        "porter_english": {
                            "type": "custom",
                            "tokenizer": "standard",
                            "filter": ["lowercase", "porter_stem"],
                        }
                    }
                },
            },
            mappings={"properties": {"text": {"type": "text", "analyzer": "porter_english"}}},
        )
        client.index(
            index=index, id="one", document={"text": "retrieval retrieving retrieved studies"}
        )
        client.indices.refresh(index=index)
        porter = client.indices.analyze(
            index=index, analyzer="porter_english", text="retrieval retrieving retrieved"
        )
        standard = client.indices.analyze(
            index=index, analyzer="standard", text="retrieval retrieving retrieved"
        )
        hit = client.search(index=index, query={"match": {"text": "retrieve"}})
        return {
            "index": index,
            "porter_tokens": [t["token"] for t in porter["tokens"]],
            "standard_tokens": [t["token"] for t in standard["tokens"]],
            "retrieve_query_hits": hit["hits"]["total"]["value"],
            "formal_indices_modified": False,
        }
    finally:
        client.indices.delete(index=index, ignore_unavailable=True)
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="backend/.runtime/porter-comparison.json")
    result = compare()
    open(parser.parse_args().output, "w", encoding="utf-8").write(
        json.dumps(result, ensure_ascii=False, indent=2)
    )
    print(json.dumps(result, ensure_ascii=False))
