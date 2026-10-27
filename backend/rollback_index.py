"""Switch an alias back to a preserved generation from an import report."""

import argparse
import json
from pathlib import Path

from backend.config import Settings, make_client
from backend.import_jsonl import publish_alias


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    alias = report["alias"]
    previous = report["previous_generations"]
    if len(previous) != 1:
        raise ValueError("rollback requires exactly one preserved previous generation")
    with make_client(Settings.from_env()) as client:
        current = list(client.indices.get_alias(name=alias))
        if current != [report["generation"]]:
            raise ValueError("active generation changed since this report; rollback stopped")
        if not client.indices.exists(index=previous[0]):
            raise ValueError("previous generation is missing")
        publish_alias(client, alias, previous[0], current)
        print(
            json.dumps(
                {
                    "alias": alias,
                    "restored": previous[0],
                    "indexed": client.count(index=alias)["count"],
                }
            )
        )


if __name__ == "__main__":
    main()
