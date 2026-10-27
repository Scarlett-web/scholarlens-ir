"""Fixed real queries and measured latency; no invented human relevance judgments."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import time

import httpx

QUERIES = [
    "magnetic resonance brain imaging",
    "how to reconstruct brain activity from MRI measurements",
    "information retrieval ranking documents",
    "protein DNA damage repair",
    "distributed computer systems",
    "soil water and citrus trees",
    "image recognition and machine learning",
    "quantum physics measurements",
]


def evaluate(base_url, output: Path, repeats=3):
    """Warm each mode once; measure identical query sets and disclose candidate semantics."""
    report = {
        "status": "measured",
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "queries": QUERIES,
        "repeats": repeats,
        "warmup_queries_per_mode": 1,
        "precision_at_5": None,
        "ndcg_at_10": None,
        "relevance_status": "no_human_judgments",
        "latency_scope": "HTTP wall-clock including embedding, ES and serialization; warmed local CPU",
        "modes": {},
    }
    with httpx.Client(base_url=base_url, timeout=120, trust_env=False) as api:
        report["index"] = api.get("/api/metrics").json()
        for mode in ("keyword", "semantic", "hybrid"):
            warm = api.get("/api/search", params={"q": QUERIES[0], "mode": mode, "page_size": 5})
            if warm.status_code != 200:
                report["modes"][mode] = {
                    "status": "dependency_unavailable",
                    "http": warm.status_code,
                }
                continue
            timings = []
            cases = []
            for _ in range(repeats):
                for q in QUERIES:
                    start = time.perf_counter()
                    r = api.get("/api/search", params={"q": q, "mode": mode, "page_size": 5})
                    elapsed = (time.perf_counter() - start) * 1000
                    r.raise_for_status()
                    body = r.json()
                    timings.append(elapsed)
                    cases.append(
                        {
                            "q": q,
                            "elapsed_ms": round(elapsed, 3),
                            "total_candidates": body["total"],
                            "top_ids": [h["paper_id"] for h in body["results"]],
                            "top_titles": [h["title"] for h in body["results"]],
                        }
                    )
            ordered = sorted(timings)
            report["modes"][mode] = {
                "status": "measured",
                "query_count": len(timings),
                "mean_ms": round(statistics.mean(timings), 3),
                "p50_ms": round(statistics.median(timings), 3),
                "p95_ms": round(
                    ordered[max(0, __import__("math").ceil(0.95 * len(ordered)) - 1)], 3
                ),
                "cases": cases,
            }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--output", default="backend/.runtime/search-evaluation.json")
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 10:
        parser.error("repeats must be1..10")
    r = evaluate(args.api, Path(args.output), args.repeats)
    print(
        json.dumps(
            {m: {k: v for k, v in d.items() if k != "cases"} for m, d in r["modes"].items()},
            indent=2,
        )
    )
