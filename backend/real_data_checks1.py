"""Reproducible representative selection and real Elasticsearch/HTTP acceptance checks."""

import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import quote

import httpx

from backend.config import Settings, make_client
from backend.app1 import SearchParams, build_search
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


def expansion(prepare_only=False):
    """Prepare local two-batch PDF configuration or verify the running expansion API.

    Missing old PDFs are explicitly expected locally. New PDF failures are fatal.
    No index writes, credential operations, or remote requests occur.
    """
    import csv
    import os
    from dataclasses import replace
    from backend.pdf_access1 import resolve_document_pdf

    root = Path(__file__).resolve().parent.parent
    output = root / "output/corpus-expansion/api-05"
    output.mkdir(parents=True, exist_ok=True)
    manifest = root / "output/corpus-expansion/prepare-02/merged_source_manifest.csv"
    rows = list(csv.DictReader(manifest.open(encoding="utf-8-sig")))
    source = root / "output/corpus-expansion/prepare-02/merged_papers.jsonl"
    records = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()]
    docs = {r["paper_id"]: r for r in records}
    settings = replace(
        Settings(),
        index="scholarlens-papers-expansion-real",
        vector_index="scholarlens-vectors-expansion-real",
        pdf_manifest_path=str(manifest),
        pdf_roots_path=str(output / "pdf-roots.json"),
    )
    if prepare_only:
        roots = {"old": None, "new": str(root / "data/ScholarLensData/extracted/kaggle_papers_PDF")}
        save_new(output / "pdf-roots.json", json_bytes(roots))
        config = {
            "ELASTICSEARCH_URL": settings.url,
            "ELASTICSEARCH_INDEX": settings.index,
            "VECTOR_INDEX": settings.vector_index,
            "EMBEDDING_MODEL_DIR": settings.model_dir,
            "SCHOLARLENS_PDF_MANIFEST": str(manifest),
            "SCHOLARLENS_PDF_ROOTS_FILE": settings.pdf_roots_path,
            "SCHOLARLENS_RUNTIME_DIR": str(root / "backend/.runtime/expansion-api"),
        }
        save_new(
            output / "local-api.env",
            ("\n".join(f"{k}={v}" for k, v in config.items()) + "\n").encode(),
        )
        checks = []
        for row in rows:
            path = resolve_document_pdf(docs[row["paper_id"]], settings)
            status = (
                "verified"
                if path
                else "not_configured_local"
                if row["source_batch"] == "old"
                else "failed"
            )
            checks.append(
                {
                    "paper_id": row["paper_id"],
                    "source_batch": row["source_batch"],
                    "source_file": row["source_file"],
                    "status": status,
                }
            )
        with (output / "pdf-mapping-checks.csv").open(
            "w", encoding="utf-8-sig", newline=""
        ) as stream:
            writer = csv.DictWriter(stream, fieldnames=list(checks[0]))
            writer.writeheader()
            writer.writerows(checks)
        assert len(rows) == len(docs) == 4000
        assert sum(r["status"] == "verified" for r in checks) == 3141
        assert sum(r["status"] == "not_configured_local" for r in checks) == 859
        print("PDF mapping: 3141 verified; old 859 not configured locally. Configuration prepared.")
        return
    evidence = {
        "status": "running",
        "checks": {},
        "old_pdf_status": "not_configured_local",
        "pdf_verified_locally": 3141,
    }
    base_url = os.getenv("EXPANSION_API_URL", "http://127.0.0.1:8000")
    if not base_url.startswith("http://127.0.0.1:"):
        raise ValueError("local API only")

    def check(name, condition):
        evidence["checks"][name] = bool(condition)
        if not condition:
            raise AssertionError(name)

    try:
        with httpx.Client(base_url=base_url, timeout=180, trust_env=False) as api:
            stats = api.get("/api/stats")
            stats.raise_for_status()
            check("stats_4000", stats.json()["indexed"] == 4000)
            caps = api.get("/api/capabilities")
            caps.raise_for_status()
            for mode in ("keyword", "semantic", "hybrid"):
                check(
                    f"{mode}_ready", caps.json()["modules"][mode + "_search"]["status"] == "ready"
                )
                response = api.get(
                    "/api/search",
                    params={"q": "information retrieval", "mode": mode, "page_size": 5},
                )
                response.raise_for_status()
                check(f"{mode}_results", bool(response.json()["results"]))
            samples = [rows[0], *[r for r in rows if r["source_batch"] == "new"][:3]]
            for i, row in enumerate(samples):
                doc = docs[row["paper_id"]]
                uri = "/api/papers/" + quote(doc["paper_id"], safe="")
                detail = api.get(uri)
                detail.raise_for_status()
                check(f"detail_{i}", detail.json()["paper_id"] == doc["paper_id"])
                found = api.get(
                    "/api/search", params={"q": doc["title"], "field": "title", "page_size": 100}
                )
                found.raise_for_status()
                check(
                    f"title_search_{i}",
                    any(r["paper_id"] == doc["paper_id"] for r in found.json()["results"]),
                )
                pdf = api.get(uri + "/pdf", headers={"Range": "bytes=0-4"})
                check(
                    f"pdf_range_{i}",
                    (pdf.status_code == 206 and pdf.content == b"%PDF-")
                    if row["source_batch"] == "new"
                    else pdf.status_code == 404,
                )
                if row["source_batch"] == "new":
                    full = api.get(uri + "/pdf")
                    full.raise_for_status()
                    check(
                        f"pdf_hash_{i}",
                        hashlib.sha256(full.content).hexdigest() == row["pdf_sha256"],
                    )
            first = api.get("/api/search", params={"q": "the", "page_size": 2}).json()
            second = api.get("/api/search", params={"q": "the", "page_size": 2, "page": 2}).json()
            check(
                "pagination",
                len(first["results"]) == len(second["results"]) == 2
                and not {r["paper_id"] for r in first["results"]}
                & {r["paper_id"] for r in second["results"]},
            )
            check("highlight", any(r.get("highlights") for r in first["results"]))
            filtered = api.get(
                "/api/search",
                params={"q": "the", "year_from": 2000, "year_to": 2020, "sort": "year_desc"},
            ).json()
            years = [r["year"] for r in filtered["results"]]
            check(
                "year_filter_sort",
                bool(years)
                and all(2000 <= y <= 2020 for y in years)
                and years == sorted(years, reverse=True),
            )
            evidence["stats"] = stats.json()
            evidence["status"] = "verified"
    except Exception:
        evidence["status"] = "failed"
        raise
    finally:
        (output / "api-verification.json").write_bytes(json_bytes(evidence))
        (output / "summary.md").write_text(
            "# 本地API验证\n\n状态："
            + evidence["status"]
            + "\n\n"
            + "\n".join(f"- {key}: {value}" for key, value in evidence["checks"].items())
            + "\n\n新增3141份PDF本地全量哈希核验；旧859份原件在服务器，本机未配置。未推送、未更新线上。\n",
            encoding="utf-8",
        )
    print(json.dumps(evidence, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    import sys

    if "--prepare-expansion" in sys.argv:
        expansion(prepare_only=True)
    elif "--verify-expansion" in sys.argv:
        expansion()
    else:
        main()
