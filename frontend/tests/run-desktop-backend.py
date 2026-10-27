"""Run upstream tests against the isolated desktop aliases, never the formal alias.

Invoke with the backend virtualenv's Python. Extra CLI arguments pass to pytest.
Only test-module Settings defaults are adapted; explicit settings stay intact.
"""
import os
from pathlib import Path
import sys

import pytest

FRONTEND_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = FRONTEND_ROOT / "dev/scholarlens-ir/zjl"
if not (BACKEND_ROOT / "backend").is_dir():
    BACKEND_ROOT = FRONTEND_ROOT.parent
if not (BACKEND_ROOT / "backend").is_dir():
    raise SystemExit("Backend root not found alongside frontend or in the desktop dev checkout")
os.chdir(BACKEND_ROOT)
sys.path.insert(0, str(BACKEND_ROOT))


class DesktopAlias:
    def pytest_collection_modifyitems(self, items):
        namespaces = [module.__dict__ for module in {item.module for item in items}]
        for item in items:
            for definitions in item._fixtureinfo.name2fixturedefs.values():
                namespaces.extend(definition.func.__globals__ for definition in definitions)
        for namespace in namespaces:
            original = namespace.get("Settings")
            if not (isinstance(original, type) and original.__name__ == "Settings"
                    and "test_" in namespace.get("__name__", "")):
                continue
            namespace["Settings"] = desktop_settings(original)


def desktop_settings(original):
    class DesktopSettings(original):
        index = "scholarlens-desktop-real"
        vector_index = "scholarlens-vectors-desktop-real"

        def __init__(self, *args, **kwargs):
            if not args:
                kwargs.setdefault("url", os.getenv("ELASTICSEARCH_URL", original.url))
                kwargs.setdefault("index", self.index)
                kwargs.setdefault("vector_index", self.vector_index)
            super().__init__(*args, **kwargs)

    return DesktopSettings


if __name__ == "__main__":
    args = sys.argv[1:] or ["backend/tests", "--basetemp=backend/.runtime/pytest-desktop",
                           "--real-alias=scholarlens-desktop-real",
                           "--real-api=http://127.0.0.1:8000", "-q", "--tb=short"]
    raise SystemExit(pytest.main(args, plugins=[DesktopAlias()]))
