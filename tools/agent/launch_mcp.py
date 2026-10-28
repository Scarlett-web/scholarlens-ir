"""Resolve this project's optional MCP interpreter without global installation."""
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
interpreter = root / "tools/agent/.venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
if not interpreter.is_file():
    raise SystemExit("Install tools/agent/requirements.txt into tools/agent/.venv first")
raise SystemExit(subprocess.call([str(interpreter), "-m", "backend.mcp_server", *sys.argv[1:]], cwd=root))
