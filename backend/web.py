"""Optional same-origin production frontend, separate from API routing."""
import re
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse


class BrowserHeadersMiddleware:
    """Add browser boundaries without buffering PDF ranges or streamed responses."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def protected_send(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                existing = {key.lower() for key, value in headers}
                defaults = {
                    b"x-content-type-options": b"nosniff",
                    b"x-frame-options": b"SAMEORIGIN",
                    b"referrer-policy": b"strict-origin-when-cross-origin",
                    b"permissions-policy": b"camera=(), microphone=(), geolocation=()",
                }
                for key, value in defaults.items():
                    if key not in existing:
                        headers.append((key, value))
                private_path = scope["path"].split("/")
                private_api = len(private_path) > 2 and private_path[1] == "api" and (
                    private_path[2] in {"auth", "me", "ai", "ask", "admin", "uploads"}
                    or any(key.lower() == b"authorization" for key, _ in scope.get("headers", []))
                )
                if private_api:
                    headers = [(key, value) for key, value in headers if key.lower() != b"cache-control"]
                    headers.append((b"cache-control", b"no-store"))
                message = {**message, "headers": headers}
            await send(message)

        return await self.app(scope, receive, protected_send)


def mount_frontend(app, directory):
    if not directory:
        return
    root = Path(directory).resolve()
    if not (root / "index.html").is_file():
        raise ValueError("FRONTEND_DIST must contain a production index.html")
    app.add_middleware(BrowserHeadersMiddleware)

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
            cache = "public, max-age=3600"
            if candidate.name == "index.html":
                cache = "no-cache"
            elif path.startswith("assets/") and re.fullmatch(r".+-[A-Za-z0-9_-]{8,}\.(?:js|css)", candidate.name):
                cache = "public, max-age=31536000, immutable"
            return FileResponse(candidate, headers={"Cache-Control": cache})
        if path.startswith(("assets/", "images/")) or "." in Path(path).name:
            raise HTTPException(404, "File not found")
        return FileResponse(root / "index.html", headers={"Cache-Control": "no-cache"})
