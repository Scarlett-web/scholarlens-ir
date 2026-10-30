"""Reproducible representative selection and real Elasticsearch/HTTP acceptance checks."""

import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import quote

import httpx

from backend.config import Settings, make_client
from backend.app import SearchParams, build_search
from backend.import_jsonl import load_jsonl
from backend.prepare_real_data import json_bytes, save_new
from backend.schema import SEARCH_FIELDS


def select_representatives(records: list[dict], size: int = 20) -> tuple[list[dict], list[dict]]:
    """Select original IDs deterministically, covering warnings and metadata edge cases."""
    selected = []
    reasons = {}

    def add(record, reason):
        if record is None:
            return
        paper_id = record["paper_id"]
        if paper_id not in reasons:
            if len(selected) >= size:
                return
            selected.append(record)
            reasons[paper_id] = []
        reasons[paper_id].append(reason)

    def first(predicate):
        return next((r for r in records if predicate(r)), None)

    for record in records:
        if "unreadable_characters_in_fulltext" in record.get("errors", []):
            add(record, "body_quality_warning_metadata_retained")
    add(
        first(lambda r: all(r.get(f) for f in SEARCH_FIELDS) and r["parse_status"] == "success"),
        "complete_metadata",
    )
    add(first(lambda r: not r["date"] and r["year"] is None), "missing_date_and_year")
    add(first(lambda r: not r["date"] and r["year"] is not None), "year_only")
    add(max(records, key=lambda r: len(r["authors"])), "many_authors")
    add(max(records, key=lambda r: len(r["affiliation"])), "many_institutions")
    add(first(lambda r: not r["address"]), "missing_address")
    add(first(lambda r: not r["affiliation"]), "missing_affiliation")
    add(first(lambda r: not r["authors"]), "missing_authors")
    add(first(lambda r: not r["abstract"]), "missing_abstract")
    add(first(lambda r: "retrieval" in r["title"].lower() and r["fulltext"]), "retrieval_terms")
    add(max(records, key=lambda r: len(r["fulltext"])), "long_body")
    add(min((r for r in records if r["fulltext"]), key=lambda r: len(r["fulltext"])), "short_body")
    for record in sorted(records, key=lambda r: r["paper_id"]):
        add(record, "deterministic_fill")
        if len(selected) == size:
            break
    if len(selected) != size:
        raise ValueError("insufficient records for representative sample")
    return selected, [
        {"paper_id": r["paper_id"], "title": r["title"], "reasons": reasons[r["paper_id"]]}
        for r in selected
    ]


def query_cases(client, generation: str, records: list[dict]) -> list[dict]:
    """Choose real field terms via the actual mapping's analyzer, never invented text."""
    candidates = sorted(
        records, key=lambda r: (not all(r.get(f) for f in SEARCH_FIELDS), r["paper_id"])
    )
    cases = []
    for field in SEARCH_FIELDS:
        record = next(r for r in candidates if r.get(field))
        value = record[field][0] if isinstance(record[field], list) else record[field]
        tokens = client.indices.analyze(index=generation, field=field, text=value[:1000])["tokens"]
        terms = list(dict.fromkeys(t["token"] for t in tokens if re.search(r"\w", t["token"])))
        q = record["date"] if field == "date" else " ".join(terms[:5])
        if not q:
            raise ValueError(f"no usable query for {field}")
        cases.append({"field": field, "q": q, "expected_id": record["paper_id"]})
    cases.append({**cases[0], "field": "all"})
    return cases


def verify_index(
    client, alias: str, input_path: Path, base_url: str, detail_ids: list[str] | None = None
) -> dict:
    """Verify every indexed source and actual HTTP behavior; raise on any assertion.

    All data values come from the delivered index input. PDF availability is tested
    as unavailable in this text-only delivery; no synthetic PDF is produced.
    """
    docs, metadata = load_jsonl(input_path, "real")
    by_id = {doc["paper_id"]: doc for doc in docs}
    alias_info = client.indices.get_alias(name=alias)
    assert len(alias_info) == 1
    generation = next(iter(alias_info))
    assert client.count(index=generation)["count"] == len(docs)
    definition = client.indices.get(index=generation)[generation]
    assert definition["mappings"]["_meta"]["data_status"] == "real"
    assert definition["settings"]["index"]["similarity"]["paper_bm25"]["type"] == "BM25"
    # mget proves all accepted IDs and all source fields, not only an aggregate count.
    for offset in range(0, len(docs), 50):
        chunk = docs[offset : offset + 50]
        indexed = client.mget(index=generation, ids=[r["paper_id"] for r in chunk])["docs"]
        assert len(indexed) == len(chunk)
        for hit in indexed:
            assert hit["found"] and hit["_source"] == by_id[hit["_id"]]
            assert not hit["_id"].startswith("mock-")
    cases = query_cases(client, generation, docs)
    evidence = {
        "alias": alias,
        "generation": generation,
        "indexed": len(docs),
        "all_sources_exact": len(docs),
        "cases": [],
        "details": [],
        "checks": {},
    }
    with httpx.Client(base_url=base_url, timeout=30, trust_env=False) as api:
        stats_response = api.get("/api/stats")
        assert stats_response.status_code == 200
        stats = stats_response.json()
        assert stats["status"] == "real" and stats["indexed"] == len(docs)
        assert stats["fields_completeness"] == metadata["fields_completeness"]
        evidence["stats"] = stats
        for case in cases:
            params = {"q": case["q"], "field": case["field"], "page_size": 100}
            response = api.get("/api/search", params=params)
            assert response.status_code == 200, response.text
            assert response.headers["X-ScholarLens-Data-Status"] == "real"
            body = response.json()
            direct = client.search(index=generation, **build_search(SearchParams(**params)))
            assert [(r["paper_id"], r["score"]) for r in body["results"]] == [
                (h["_id"], h["_score"]) for h in direct["hits"]["hits"]
            ]
            all_hits = list(body["results"])
            for page in range(2, (body["total"] + 99) // 100 + 1):
                additional = api.get("/api/search", params={**params, "page": page})
                assert additional.status_code == 200
                all_hits.extend(additional.json()["results"])
            ids = [hit["paper_id"] for hit in all_hits]
            assert case["expected_id"] in ids
            assert len(set(ids)) == len(ids) == body["total"]
            assert all(hit["score"] > 0 for hit in all_hits)
            scores = [hit["score"] for hit in all_hits]
            assert scores == sorted(scores, reverse=True)
            expected = next(hit for hit in all_hits if hit["paper_id"] == case["expected_id"])
            if case["field"] != "all":
                assert case["field"] in expected["matched_fields"]
            assert any(
                "<em>" in fragment
                for fragments in expected["highlights"].values()
                for fragment in fragments
            )
            evidence["cases"].append(
                {
                    **case,
                    "http": 200,
                    "total": body["total"],
                    "expected_rank": ids.index(case["expected_id"]) + 1,
                    "first_result": body["results"][0],
                    "took_ms": body["took_ms"],
                }
            )
        common = "the"
        date_case = next(case for case in cases if case["field"] == "date")
        date_year = api.get(
            "/api/search", params={"q": date_case["q"][:4], "field": "date", "page_size": 100}
        )
        assert date_year.status_code == 200
        assert any(h["paper_id"] == date_case["expected_id"] for h in date_year.json()["results"])
        evidence["checks"]["date_year_query"] = {
            "q": date_case["q"][:4],
            "total": date_year.json()["total"],
            "expected_id": date_case["expected_id"],
        }
        paged = api.get("/api/search", params={"q": common, "field": "all", "page_size": 2}).json()
        if paged["total"] < 3:
            common = "of"
            paged = api.get("/api/search", params={"q": common, "page_size": 2}).json()
        assert paged["total"] >= 3
        ranking = api.get("/api/search", params={"q": common, "field": "all", "page_size": 10})
        assert ranking.status_code == 200
        ranked = ranking.json()["results"]
        ranking_direct = client.search(
            index=generation, **build_search(SearchParams(q=common, page_size=10))
        )
        assert [(r["paper_id"], r["score"]) for r in ranked] == [
            (h["_id"], h["_score"]) for h in ranking_direct["hits"]["hits"]
        ]
        assert len(ranked) >= 3 and [r["score"] for r in ranked] == sorted(
            (r["score"] for r in ranked), reverse=True
        )
        evidence["checks"]["multi_hit_bm25"] = {
            "q": common,
            "total": ranking.json()["total"],
            "top": [{"paper_id": r["paper_id"], "score": r["score"]} for r in ranked],
        }
        second = api.get("/api/search", params={"q": common, "page_size": 2, "page": 2}).json()
        assert not {r["paper_id"] for r in paged["results"]} & {
            r["paper_id"] for r in second["results"]
        }
        evidence["checks"]["pagination"] = {
            "q": common,
            "total": paged["total"],
            "first": [r["paper_id"] for r in paged["results"]],
            "second": [r["paper_id"] for r in second["results"]],
        }
        for sort in ("year_asc", "year_desc"):
            response = api.get("/api/search", params={"q": common, "sort": sort, "page_size": 100})
            assert response.status_code == 200
            years = [r["year"] for r in response.json()["results"]]
            known = [year for year in years if year is not None]
            assert known == sorted(known, reverse=sort == "year_desc")
            assert years == known + [None] * (len(years) - len(known))
        year_record = next(r for r in docs if r["year"] and r["title"])
        year = year_record["year"]
        filtered = api.get(
            "/api/search",
            params={
                "q": " ".join(year_record["title"].split()[:3]),
                "year_from": year,
                "year_to": year,
                "page_size": 100,
            },
        )
        assert filtered.status_code == 200 and filtered.json()["total"] > 0
        assert all(r["year"] == year for r in filtered.json()["results"])
        evidence["checks"]["year_filter"] = {"year": year, "total": filtered.json()["total"]}
        year_only = next(
            (record for record in docs if record["year"] is not None and "date" not in record), None
        )
        if year_only is not None:
            terms = client.indices.analyze(
                index=generation, field="title", text=year_only["title"]
            )["tokens"]
            q = " ".join(dict.fromkeys(t["token"] for t in terms[:5]))
            filtered = api.get(
                "/api/search",
                params={
                    "q": q,
                    "field": "title",
                    "year_from": year_only["year"],
                    "year_to": year_only["year"],
                    "page_size": 100,
                },
            )
            assert filtered.status_code == 200 and any(
                h["paper_id"] == year_only["paper_id"] for h in filtered.json()["results"]
            )
            vectors = client.termvectors(
                index=generation,
                id=year_only["paper_id"],
                fields=["date"],
                term_statistics=False,
                field_statistics=False,
            )
            assert not vectors.get("term_vectors", {}).get("date", {}).get("terms")
            evidence["checks"]["year_only_without_fake_date"] = {
                "paper_id": year_only["paper_id"],
                "year": year_only["year"],
                "retrieved": True,
            }
        selected = detail_ids or [
            record["paper_id"]
            for record in select_representatives(
                [
                    json.loads(line)
                    for line in input_path.read_text(encoding="utf-8-sig").splitlines()
                ]
            )[0]
        ]
        public = (
            "paper_id",
            "title",
            "authors",
            "date",
            "year",
            "affiliation",
            "address",
            "abstract",
            "fulltext",
            "pages",
        )
        for paper_id in selected:
            route = "/api/papers/" + quote(paper_id, safe="")
            response = api.get(route)
            assert response.status_code == 200, response.text
            detail = response.json()
            original = by_id[paper_id]
            for field in public:
                assert detail[field] == original.get(field, "" if field in ("date",) else None), (
                    paper_id,
                    field,
                )
            assert (
                detail["pdf_available"] is False
                and detail["source_status"]["pdf"] == "pdf_not_available"
            )
            assert detail["source_status"]["parse_status"] == original["parse_status"]
            assert not {"pdf_path", "source_file", "errors"} & detail.keys()
            pdf = api.get(route + "/pdf")
            assert pdf.status_code == 404 and pdf.json()["error"]["code"] == "pdf_not_available"
            evidence["details"].append(
                {
                    "paper_id": paper_id,
                    "title": detail["title"],
                    "fields_exact": True,
                    "parse_status": detail["source_status"]["parse_status"],
                    "pdf_http": 404,
                    "empty_date": not detail["date"],
                    "empty_address": not detail["address"],
                    "body_characters": len(detail["fulltext"]),
                }
            )
        body_isolated = []
        for doc in docs:
            if "unreadable_characters_in_fulltext" not in doc["errors"]:
                continue
            assert doc["fulltext"] == ""
            vectors = client.termvectors(
                index=generation,
                id=doc["paper_id"],
                fields=["fulltext"],
                term_statistics=False,
                field_statistics=False,
            )
            # ES exists also treats empty strings as existing; verify zero searchable terms.
            assert not vectors.get("term_vectors", {}).get("fulltext", {}).get("terms")
            body_isolated.append(doc["paper_id"])
        evidence["checks"]["body_quarantine"] = body_isolated
        empty = api.get("/api/search", params={"q": "scholarlenszznoresults984512"})
        assert empty.status_code == 200 and empty.json()["total"] == 0
        for params in ({"q": "x", "page_size": 101}, {"q": " "}, {"q": "x", "field": "bad"}):
            response = api.get("/api/search", params=params)
            assert (
                response.status_code == 400
                and response.json()["error"]["code"] == "invalid_parameter"
            )
        missing = api.get("/api/papers/source-sha256:not-in-delivery")
        assert missing.status_code == 404 and missing.json()["error"]["code"] == "paper_not_found"
        evidence["checks"].update(
            bm25=True,
            year_sort=True,
            empty_result=True,
            invalid_parameters=True,
            paper_not_found=True,
        )
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sample = sub.add_parser("select")
    sample.add_argument("--input", type=Path, required=True)
    sample.add_argument("--output", type=Path, required=True)
    sample.add_argument("--selection", type=Path, required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--input", type=Path, required=True)
    verify.add_argument("--alias", required=True)
    verify.add_argument("--base-url", required=True)
    verify.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "select":
        records = [
            json.loads(line) for line in args.input.read_text(encoding="utf-8-sig").splitlines()
        ]
        selected, reasons = select_representatives(records)
        payload = ("\n".join(json.dumps(r, ensure_ascii=False) for r in selected) + "\n").encode()
        save_new(args.output, payload)
        save_new(
            args.selection,
            json_bytes(
                {
                    "input_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
                    "selected": reasons,
                }
            ),
        )
        print(json.dumps({"selected": len(selected), "ids_preserved": True}))
    else:
        with make_client(Settings(index=args.alias)) as client:
            result = verify_index(client, args.alias, args.input, args.base_url)
        save_new(args.report, json_bytes(result))
        print(
            json.dumps(
                {
                    "alias": args.alias,
                    "verified_sources": result["all_sources_exact"],
                    "field_cases": len(result["cases"]),
                    "details": len(result["details"]),
                    "checks": {key: True for key in result["checks"]},
                }
            )
        )


if __name__ == "__main__":
    main()
