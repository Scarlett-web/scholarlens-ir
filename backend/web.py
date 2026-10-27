"""Optional same-origin production frontend, separate from API routing."""
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse


def mount_frontend(app, directory):
    if not directory:
        return
    root = Path(directory).resolve()
    if not (root / "index.html").is_file():
        raise ValueError("FRONTEND_DIST must contain a production index.html")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "API route not found")
        if any(part.startswith(".") for part in path.split("/") if part):
            raise HTTPException(404, "File not found")
        candidate = (root / path).resolve()
        if not candidate.is_relative_to(root):
            raise HTTPException(404, "File not found")
        if candidate.is_file():
            return FileResponse(candidate, headers={"X-Content-Type-Options": "nosniff",
                "Cache-Control": "no-cache" if candidate.name == "index.html" else "public, max-age=3600"})
        if path.startswith(("assets/", "images/")) or "." in Path(path).name:
            raise HTTPException(404, "File not found")
        return FileResponse(root / "index.html", headers={"Cache-Control": "no-cache"})
