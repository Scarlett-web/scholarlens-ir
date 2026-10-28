"""Request-scoped personal credentials and a DNS-pinned public HTTPS transport."""
from dataclasses import replace
import ipaddress
import socket
from urllib.parse import urlsplit

import httpx

from backend.accounts import problem


def personal_settings(settings, headers, authenticate, require_model=True):
    """Authenticate before using personal headers; never persist or echo secrets."""
    fields = [headers.get("x-scholarlens-ai-" + name, "") for name in ("url", "model", "key", "token-parameter", "protocol")]
    if not any(fields):
        return settings
    authenticate()
    url, model, key, parameter, protocol = (value.strip() for value in fields)
    if not url or (require_model and not model) or not key or len(url) > 2048 or len(model) > 200 or len(key) > 2048:
        raise problem(400, "invalid_ai_configuration", "请填写完整的 API URL、模型与密钥")
    if any(ord(c) < 33 or ord(c) > 126 for c in model + key):
        raise problem(400, "invalid_ai_configuration", "模型和密钥不能含空白或非ASCII字符")
    try:
        parsed = urlsplit(url)
        port = parsed.port
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.query or parsed.fragment
                or port not in (None, 443) or "\\" in url or any(ord(c) < 33 for c in url)):
            raise ValueError()
        normalized = str(httpx.URL(url)).rstrip("/")
    except (ValueError, httpx.InvalidURL):
        raise problem(400, "invalid_ai_configuration", "个人 API 需要公共 HTTPS 地址（443端口），不要附带账号、查询参数或片段")
    if protocol and protocol not in ("chat_completions", "responses"):
        raise problem(400, "invalid_ai_configuration", "请选择 Chat Completions 或 Responses 协议")
    for suffix, kind in (("/chat/completions", "chat_completions"), ("/responses", "responses")):
        if normalized.endswith(suffix):
            normalized = normalized[:-len(suffix)]
            protocol = kind
            break
    protocol = protocol or "chat_completions"
    if protocol not in ("chat_completions", "responses"):
        raise problem(400, "invalid_ai_configuration", "请选择 Chat Completions 或 Responses 协议")
    parameter = parameter or "max_completion_tokens"
    if parameter not in ("max_tokens", "max_completion_tokens"):
        raise problem(400, "invalid_ai_configuration", "不支持的 token 参数")
    return replace(settings, ai_base_url=normalized, ai_model=model, ai_api_key=key,
                   ai_token_parameter=parameter, ai_protocol=protocol,
                   ai_timeout=max(settings.ai_timeout, 60), ai_personal=True)


class PublicAITransport(httpx.BaseTransport):
    """Resolve once per request, reject private results, then dial the validated IP.

    Original Host and TLS SNI remain intact, including certificate verification.
    Redirects are disabled by the caller. No environment proxies are used.
    """
    def __init__(self):
        self.inner = httpx.HTTPTransport(retries=0)

    def handle_request(self, request):
        hostname = request.url.host
        try:
            addresses = list(dict.fromkeys(row[4][0] for row in socket.getaddrinfo(
                hostname, 443, type=socket.SOCK_STREAM)))
        except OSError:
            raise httpx.ConnectError("AI hostname lookup failed", request=request) from None
        if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
            raise problem(400, "unsafe_ai_endpoint", "个人 API 地址不能指向本机、内网或保留网络")
        headers = httpx.Headers(request.headers)
        headers["Host"] = request.url.netloc.decode("ascii")
        pinned = httpx.Request(request.method, request.url.copy_with(host=addresses[0]),
                               headers=headers, stream=request.stream,
                               extensions={**request.extensions, "sni_hostname": hostname})
        return self.inner.handle_request(pinned)

    def close(self):
        self.inner.close()
