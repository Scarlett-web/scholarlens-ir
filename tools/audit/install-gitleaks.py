"""Install the pinned Windows x64 audit binary locally; verify before execution."""
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

VERSION = "8.30.1"
ARCHIVE_SHA256 = "d29144deff3a68aa93ced33dddf84b7fdc26070add4aa0f4513094c8332afc4e"
BINARY_SHA256 = "17157e2ee8b76fc8b1d8bee607a250e34b8a8023c8bc81822d4b5ee4d78fcb7c"


def main() -> None:
    """Download from the official release and only install the expected executable."""
    root = Path(__file__).resolve().parent
    binary = root / "bin" / "gitleaks.exe"
    if binary.exists():
        if hashlib.sha256(binary.read_bytes()).hexdigest() != BINARY_SHA256:
            raise SystemExit("Existing binary differs; preserve and inspect it before replacement.")
        print(f"Verified existing project-local Gitleaks {VERSION}")
        return
    curl = shutil.which("curl.exe")
    if not curl:
        raise SystemExit("This installer targets Windows x64 and requires curl.exe.")
    downloads = root / ".downloads"
    downloads.mkdir(exist_ok=True)
    archive = downloads / f"gitleaks_{VERSION}_windows_x64.zip"
    url = f"https://github.com/gitleaks/gitleaks/releases/download/v{VERSION}/{archive.name}"
    subprocess.run([curl, "--fail", "--silent", "--show-error", "--location", "--max-time", "60", "--output", str(archive), url], check=True)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != ARCHIVE_SHA256:
        raise SystemExit("Official release archive hash mismatch; nothing executed.")
    with zipfile.ZipFile(archive) as zipped:
        if zipped.namelist().count("gitleaks.exe") != 1:
            raise SystemExit("Expected one gitleaks.exe entry.")
        data = zipped.read("gitleaks.exe")
    if hashlib.sha256(data).hexdigest() != BINARY_SHA256:
        raise SystemExit("Executable hash mismatch; nothing executed.")
    binary.parent.mkdir(exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=binary.parent, suffix=".tmp")
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)
    os.replace(temporary, binary)
    (binary.parent / "provenance.json").write_text(json.dumps({"version": VERSION, "source": url, "archive_sha256": ARCHIVE_SHA256, "binary_sha256": BINARY_SHA256}, indent=2), encoding="utf-8")
    print(f"Installed project-local Gitleaks {VERSION}; archive and binary hashes verified.")


if __name__ == "__main__":
    main()
