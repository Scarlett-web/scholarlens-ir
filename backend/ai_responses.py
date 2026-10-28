"""Validate untrusted Chat Completions JSON before it reaches agent callbacks."""
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
