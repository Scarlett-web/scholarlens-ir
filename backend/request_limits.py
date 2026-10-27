"""Reject unauthorized/oversized upload bodies before multipart disk spooling."""

from fastapi.responses import JSONResponse

from backend.accounts import problem


class UploadLimitMiddleware:
    def __init__(self, app, store, max_bytes=21 * 1024 * 1024):
        self.app = app
        self.store = store
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope["path"] not in ("/api/uploads", "/api/admin/uploads", "/api/me/avatar")
            or scope["method"] != "POST"
        ):
            return await self.app(scope, receive, send)
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        try:
            user = self.store.authenticate(headers.get("authorization"))
            if scope["path"] == "/api/admin/uploads" and user["role"] != "admin":
                raise problem(403, "forbidden", "需要管理员权限")
            length = headers.get("content-length")
            if length is not None:
                try:
                    value = int(length)
                except ValueError:
                    raise problem(400, "invalid_parameter", "Content-Length无效")
                if value < 0:
                    raise problem(400, "invalid_parameter", "Content-Length无效")
                if value > self.max_bytes:
                    raise problem(413, "file_too_large", "上传请求体最大21MiB，PDF最大20MiB")
        except Exception as e:
            if not hasattr(e, "status_code"):
                raise
            return await JSONResponse({"error": e.detail}, status_code=e.status_code)(
                scope, receive, send
            )
        consumed = 0

        async def bounded_receive():
            nonlocal consumed
            message = await receive()
            consumed += len(message.get("body", b""))
            if consumed > self.max_bytes:
                raise problem(413, "file_too_large", "上传请求体最大21MiB，PDF最大20MiB")
            return message

        return await self.app(scope, bounded_receive, send)
