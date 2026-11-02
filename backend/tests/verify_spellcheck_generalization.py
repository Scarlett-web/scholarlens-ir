"""Read-only real-corpus spelling sweep; writes a report, never corpus data."""

import argparse
import json
from pathlib import Path
import time
from urllib.parse import urlparse

import httpx


def verify(base_url: str, output: Path) -> dict:
    """Generate multiple error types from known phrases and report every outcome."""
    if urlparse(base_url).hostname not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("local API only")
    cases = [("screenshot", "machein learning", "machine learning")]
    for phrase in (
        "machine learning",
        "information retrieval",
        "neural networks",
        "quantum computing",
        "magnetic resonance",
        "climate change",
        "information retrieval systems",
    ):
        first, *tail = phrase.split()
        i = len(first) // 2
        mutations = {
            "deletion": first[:i] + first[i + 1 :],
            "insertion": first[:i] + "x" + first[i:],
            "substitution": first[:i] + "x" + first[i + 1 :],
            "adjacent_swap": first[:i] + first[i + 1] + first[i] + first[i + 2 :],
            "two_substitutions": first[:1] + first[-1] + first[2:-1] + first[1],
        }
        for kind, value in mutations.items():
            cases.append((kind, " ".join([value, *tail]), phrase))
        wrong_words = [word[:2] + word[3] + word[2] + word[4:] for word in phrase.split()]
        cases.append(("multiple_words", " ".join(wrong_words), phrase))
        cases.append(("missing_space", phrase.replace(" ", "", 1), phrase))
        cases.append(("extra_space", first[:3] + " " + first[3:] + " " + " ".join(tail), phrase))
    # Swapping identical letters is not a spelling error; exclude unchanged inputs.
    cases = [case for case in cases if case[1] != case[2]]
    outcomes = []
    with httpx.Client(base_url=base_url, timeout=90, trust_env=False) as client:
        stats = client.get("/api/stats").json()
        for kind, wrong, expected in cases:
            valid = client.get("/api/search", params={"q": expected, "page_size": 1})
            valid.raise_for_status()
            if valid.json()["total"] == 0:
                outcomes.append(
                    {"kind": kind, "wrong": wrong, "expected": expected, "status": "target_absent"}
                )
                continue
            original = client.get("/api/search", params={"q": wrong, "page_size": 1})
            original.raise_for_status()
            started = time.monotonic()
            response = client.get("/api/spellcheck", params={"q": wrong, "limit": 3})
            response.raise_for_status()
            suggestions = response.json()["suggestions"]
            status = (
                "original_has_results"
                if original.json()["total"]
                else "passed"
                if any(s["text"].casefold() == expected.casefold() for s in suggestions)
                else "missed"
            )
            outcomes.append(
                {
                    "kind": kind,
                    "wrong": wrong,
                    "expected": expected,
                    "status": status,
                    "suggestions": suggestions,
                    "seconds": round(time.monotonic() - started, 3),
                }
            )
    report = {
        "papers": stats["indexed"],
        "cases": len(outcomes),
        "passed": sum(r["status"] == "passed" for r in outcomes),
        "missed": sum(r["status"] == "missed" for r in outcomes),
        "original_has_results": sum(r["status"] == "original_has_results" for r in outcomes),
        "target_absent": sum(r["status"] == "target_absent" for r in outcomes),
        "outcomes": outcomes,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/corpus-expansion/spellcheck-08/generalization/real-corpus.json"),
    )
    args = parser.parse_args()
    result = verify(args.url, args.output)
    print(json.dumps({k: v for k, v in result.items() if k != "outcomes"}, indent=2))
    for row in result["outcomes"]:
        if row["status"] == "missed":
            print(row["wrong"], "=>", [s["text"] for s in row["suggestions"]])
    raise SystemExit(1 if result["missed"] else 0)
