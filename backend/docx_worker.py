"""Child process entry: all PDF parsing is bounded by the caller's wall-clock timeout."""

from pathlib import Path
import sys

from backend.docx_convert import convert_local

if __name__ == "__main__":
    try:
        convert_local(Path(sys.argv[1]), Path(sys.argv[2]))
    except Exception as exc:
        print(
            getattr(exc, "detail", {}).get("code", "conversion_failed")
            if isinstance(getattr(exc, "detail", {}), dict)
            else "conversion_failed"
        )
        raise SystemExit(1)
