"""Protocol payloads and strict text decoding at the untrusted provider boundary."""
import json


def json_object(raw: str | bytes | bytearray) -> dict:
    """Require an object and normalize excessive nesting at the JSON boundary."""
    if not isinstance(raw, (str, bytes, bytearray)):
        raise ValueError("Expected JSON text")
    try:
        value = json.loads(raw)
    except RecursionError:
        raise ValueError("JSON nesting exceeds the decoder limit") from None
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def chat_content(raw: str | bytes | bytearray) -> str:
    """Accept text replies only; never stringify tools or multimodal content."""
    envelope = json_object(raw)
    choices = envelope.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ValueError("Expected a completion choice")
    message = choices[0].get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise ValueError("Expected message text")
    return message["content"]


def provider_request(settings, messages: list[dict], max_tokens: int):
    """Build one explicit protocol request; never silently switch models or retry protocols."""
    if settings.ai_protocol == "responses":
        return settings.ai_base_url.rstrip("/") + "/responses", {
            "model": settings.ai_model, "input": messages, "stream": False,
            "store": False, "max_output_tokens": max_tokens,
        }
    if settings.ai_protocol != "chat_completions" or settings.ai_token_parameter not in ("max_tokens", "max_completion_tokens"):
        raise ValueError("Unsupported provider protocol")
    return settings.ai_base_url.rstrip("/") + "/chat/completions", {
        "model": settings.ai_model, "messages": messages, "stream": False,
        settings.ai_token_parameter: max_tokens,
    }


def provider_content(raw: str | bytes | bytearray, protocol: str) -> str:
    """Read completed assistant text only, excluding reasoning, tools and partial output."""
    if protocol == "chat_completions":
        return chat_content(raw)
    if protocol != "responses":
        raise ValueError("Unsupported provider protocol")
    envelope = json_object(raw)
    if envelope.get("status") != "completed" or envelope.get("error") or envelope.get("incomplete_details"):
        raise ValueError("Response did not complete")
    output = envelope.get("output")
    if not isinstance(output, list):
        raise ValueError("Expected response output")
    parts = []
    for item in output:
        if not isinstance(item, dict):
            raise ValueError("Invalid output item")
        if item.get("type") != "message":
            continue
        if item.get("role") != "assistant" or item.get("status", "completed") != "completed" or not isinstance(item.get("content"), list):
            raise ValueError("Expected completed assistant message")
        for part in item["content"]:
            if not isinstance(part, dict) or part.get("type") != "output_text" or not isinstance(part.get("text"), str):
                raise ValueError("Expected output text")
            parts.append(part["text"])
    if not parts or not "".join(parts).strip():
        raise ValueError("Empty response text")
    return "\n".join(parts)
