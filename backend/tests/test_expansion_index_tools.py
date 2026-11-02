"""Offline guard tests; never touches Elasticsearch or production configuration."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from backend.import_jsonl1 import PAPERS, VECTORS, check_input, validate_alias, validate_url


class ExpansionIndexTests(unittest.TestCase):
    def test_protected_aliases_and_remote_cluster_rejected(self):
        validate_alias(PAPERS)
        validate_alias(VECTORS, vector=True)
        for alias, vector in (
            ("scholarlens-papers-real", False),
            ("scholarlens-vectors-real", True),
            (PAPERS, True),
        ):
            with self.assertRaises(ValueError):
                validate_alias(alias, vector)
        validate_url("http://127.0.0.1:9200")
        for url in (
            "https://example.com",
            "http://user:pass@localhost:9200",
            "http://localhost:9200/other",
        ):
            with self.assertRaises(ValueError):
                validate_url(url)

    def test_stale_input_duplicate_ids_and_count_rejected(self):
        test_root = Path("output/corpus-expansion/tests")
        test_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=test_root) as directory:
            root = Path(directory)
            path, summary = root / "input.jsonl", root / "summary.json"
            record = {"paper_id": "paper-a", "parse_status": "success"}
            raw = (json.dumps(record) + "\n").encode()
            path.write_bytes(raw)

            def write_summary(data, count):
                summary.write_text(
                    json.dumps(
                        {
                            "records": count,
                            "outputs": {
                                "merged_papers.jsonl": {"sha256": hashlib.sha256(data).hexdigest()}
                            },
                        }
                    ),
                    encoding="utf-8",
                )

            write_summary(raw, 1)
            self.assertEqual(check_input(path, summary, 1)["records"], 1)
            with self.assertRaises(ValueError):
                check_input(path, summary, 2)
            path.write_bytes(raw + b"\n")
            with self.assertRaises(ValueError):
                check_input(path, summary, 1)
            path.write_bytes(raw + raw)
            write_summary(raw + raw, 2)
            with self.assertRaises(ValueError):
                check_input(path, summary, 2)


if __name__ == "__main__":
    unittest.main()
