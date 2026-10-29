"""Small controlled audit fixtures; never touches the real corpus or ES."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.corpus_expansion.audit_expansion import audit


class AuditTests(unittest.TestCase):
    def test_cross_matches_hash_failure_and_output_protection(self):
        test_root = Path("output/corpus-expansion/tests")
        test_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=test_root) as folder:
            root = Path(folder)
            pdf = b"%PDF-1.4\nfixture"
            pdf_hash = hashlib.sha256(pdf).hexdigest()
            (root / "a.pdf").write_bytes(pdf)
            (root / "b.pdf").write_bytes(b"%PDF-wrong")
            for batch, records in {
                "old": [{"paper_id": "old-id", "source_file": "a.pdf", "title": "Same Title", "pdf_path": "a.pdf", "parse_status": "success"}],
                "new": [{"paper_id": "new-id", "source_file": "a.pdf", "title": " SAME  TITLE ", "pdf_path": "a.pdf", "parse_status": "success"},
                        {"paper_id": "old-id", "source_file": "b.pdf", "title": "Other", "pdf_path": "b.pdf", "parse_status": "error"}],
            }.items():
                (root / f"{batch}.jsonl").write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
                with (root / f"{batch}.csv").open("w", newline="", encoding="utf-8") as stream:
                    writer = csv.DictWriter(stream, fieldnames=["paper_id", "source_file", "pdf_path", "pdf_sha256"])
                    writer.writeheader()
                    writer.writerows({**{key: r[key] for key in ("paper_id", "source_file", "pdf_path")}, "pdf_sha256": pdf_hash} for r in records)
            args = argparse.Namespace(new_jsonl=root / "new.jsonl", new_manifest=root / "new.csv", old_jsonl=root / "old.jsonl", old_manifest=root / "old.csv", old_git_ref=None, expected_old=1, expected_new=2, pdf_root=root, output=root / "report")
            result = audit(args)
            self.assertEqual(result["cross_batch_matches"]["paper_id"]["new_records"], 1)
            self.assertEqual(result["cross_batch_matches"]["pdf_sha256"]["new_records"], 2)
            self.assertEqual(result["cross_batch_matches"]["normalized_title"]["new_records"], 1)
            self.assertEqual(result["cross_batch_matches"]["normalized_fulltext"]["pairs"], 0)
            self.assertEqual(result["pdf_status"], {"verified": 1, "hash_mismatch": 1})
            self.assertEqual(result["errors"], 2)
            with self.assertRaises(ValueError):
                audit(args)


if __name__ == "__main__":
    unittest.main()
