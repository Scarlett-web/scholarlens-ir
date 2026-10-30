"""Verify preservation and rejection of stale/ambiguous merge inputs."""

import argparse
import importlib
import json
import tempfile
import unittest
from pathlib import Path

module = importlib.import_module("tools.corpus_expansion.02_prepare_expansion")


class PrepareTests(unittest.TestCase):
    def test_preservation_stale_audit_and_conflict(self):
        test_root = Path("output/corpus-expansion/tests")
        test_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=test_root) as folder:
            root = Path(folder)
            records = {}
            for batch, digit in (("old", "1"), ("new", "2")):
                record = {
                    "paper_id": batch,
                    "source_file": f"{batch}.pdf",
                    "pdf_path": f"original/{batch}.pdf",
                    "fulltext": "text\ufffd" if batch == "new" else "body",
                    "parse_status": "partial",
                }
                records[batch] = record
                (root / f"{batch}.jsonl").write_text(
                    json.dumps(record) + "\n", encoding="utf-8"
                )
                (root / f"{batch}.csv").write_bytes(
                    module.csv_bytes(
                        [
                            {
                                **{
                                    f: record[f]
                                    for f in ("paper_id", "source_file", "pdf_path")
                                },
                                "pdf_sha256": digit * 64,
                            }
                        ],
                        ["paper_id", "source_file", "pdf_path", "pdf_sha256"],
                    )
                )

            def write_audit():
                summary = {
                    "errors": 0,
                    "provenance": {
                        batch: {
                            "jsonl_sha256": module.sha256(
                                (root / f"{batch}.jsonl").read_bytes()
                            ),
                            "manifest_sha256": module.sha256(
                                (root / f"{batch}.csv").read_bytes()
                            ),
                            "valid_records": 1,
                        }
                        for batch in ("old", "new")
                    },
                }
                (root / "summary.json").write_text(
                    json.dumps(summary), encoding="utf-8"
                )

            write_audit()
            args = argparse.Namespace(
                old_jsonl=root / "old.jsonl",
                old_manifest=root / "old.csv",
                new_jsonl=root / "new.jsonl",
                new_manifest=root / "new.csv",
                audit_dir=root,
                old_git_ref=None,
                expected_old=1,
                expected_new=1,
                output=root / "merged",
            )
            summary = module.prepare(args)
            result = [
                json.loads(line)
                for line in (args.output / "merged_papers.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(result, [records["old"], records["new"]])
            self.assertEqual(summary["quarantine_on_import"], {"old": 0, "new": 1})
            with self.assertRaises(ValueError):
                module.prepare(args)
            args.output = root / "stale"
            args.new_jsonl.write_text(
                json.dumps(records["new"]) + "\n\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "sources differ"):
                module.prepare(args)
            self.assertFalse(args.output.exists())
            args.new_manifest.write_bytes(
                args.new_manifest.read_bytes().replace(b"2" * 64, b"1" * 64)
            )
            write_audit()
            with self.assertRaisesRegex(ValueError, "PDF hash conflict"):
                module.prepare(args)
            self.assertFalse(args.output.exists())


if __name__ == "__main__":
    unittest.main()
