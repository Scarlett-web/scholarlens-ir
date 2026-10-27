"""Hash-guarded source-only rollback; never touch data, databases, models or ES."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile


def digest(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def rollback(root: Path, snapshot: Path, manifest: Path, apply=False):
    """Validate every target before restoring any bytes; newer edits stop the rollback."""
    root = root.resolve()
    rows = json.loads(manifest.read_text(encoding="utf-8"))["changes"]
    actions = []
    with zipfile.ZipFile(snapshot) as archive:
        for row in rows:
            relative = PurePosixPath(row["path"])
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or ":" in row["path"]
                or "\\" in row["path"]
            ):
                raise ValueError("invalid relative rollback path")
            target = (root / str(relative)).resolve()
            if not target.is_relative_to(root):
                raise ValueError("rollback target escapes root")
            current = digest(target)
            if current == row["before_sha256"]:
                continue
            if current != row["after_sha256"]:
                raise ValueError("source changed after verification: " + str(relative))
            original = None if row["before_sha256"] is None else archive.read(str(relative))
            if (
                original is not None
                and hashlib.sha256(original).hexdigest() != row["before_sha256"]
            ):
                raise ValueError("snapshot hash mismatch")
            actions.append((target, original))
        if apply:
            for target, original in actions:
                if original is None:
                    target.unlink()  # A single verified newly added source file only.
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(original)
    return {
        "mode": "applied" if apply else "check",
        "files": len(actions),
        "preserved": "all ES indices, original files, SQLite, uploads, models, env and dependencies",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--snapshot", type=Path, default=Path("backend/.runtime/v2-before.zip"))
    parser.add_argument(
        "--manifest", type=Path, default=Path("backend/.runtime/v2-source-manifest.json")
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(rollback(args.root, args.snapshot, args.manifest, args.apply), indent=2))
