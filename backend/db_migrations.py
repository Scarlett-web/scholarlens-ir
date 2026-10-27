"""SQLite online backups and operator-only restoration with a preserved pre-restore copy."""

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid


VERSION = 4


def backup_before_upgrade(path: Path):
    if not path.exists():
        return None
    with sqlite3.connect(path) as source:
        exists = source.execute(
            "SELECT 1 FROM sqlite_master WHERE name='schema_version'"
        ).fetchone()
        version = (
            source.execute("SELECT version FROM schema_version").fetchone()[0] if exists else 0
        )
        if version >= VERSION:
            return None
        directory = path.parent / "db-backups"
        directory.mkdir(exist_ok=True)
        dest = directory / f"before-v{VERSION}-{uuid.uuid4().hex}.sqlite3"
        with sqlite3.connect(dest) as target:
            source.backup(target)
            assert target.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    digest = hashlib.sha256(dest.read_bytes()).hexdigest()
    dest.with_suffix(".json").write_text(
        json.dumps(
            {
                "source_version": version,
                "target_version": VERSION,
                "sha256": digest,
                "backup": dest.name,
            }
        ),
        encoding="utf-8",
    )
    return dest


def restore(path: Path, backup: Path):
    """API must be stopped. Preserve current DB, restore using SQLite backup including WAL."""
    if path.resolve() == backup.resolve():
        raise ValueError("backup and destination must differ")
    if not backup.is_file():
        raise FileNotFoundError("backup not found")
    with sqlite3.connect(backup) as source:
        if source.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("backup is not valid")
        preserved = path.with_name("before-restore-" + uuid.uuid4().hex + ".sqlite3")
        with sqlite3.connect(path) as current, sqlite3.connect(preserved) as saved:
            current.backup(saved)
            source.backup(current)
    return {"restored": True, "preserved_file": preserved.name}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Stop the API first; restore only a private SQLite backup"
    )
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--restore", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(restore(args.database, args.restore)))
