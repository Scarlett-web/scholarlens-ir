"""Keep Starlette's Range implementation while normalizing its range errors to JSON."""

from fastapi.responses import FileResponse, JSONResponse


class PDFResponse(FileResponse):
    async def __call__(self, scope, receive, send):
        replaced = False

        async def normalized_send(message):
            nonlocal replaced
            if message["type"] == "http.response.start" and message["status"] in (400, 416):
                replaced = True
                status = message["status"]
                headers = {
                    k.decode(): v.decode()
                    for k, v in message["headers"]
                    if k.lower() == b"content-range"
                }
                response = JSONResponse(
                    {
                        "error": {
                            "code": "range_not_satisfiable"
                            if status == 416
                            else "invalid_parameter",
                            "message": "PDF字节范围无效，请重新请求文件",
                            "details": {},
                        }
                    },
                    status_code=status,
                    headers=headers,
                )
                await response(scope, receive, send)
            elif not replaced:
                await send(message)

        return await super().__call__(scope, receive, normalized_send)
