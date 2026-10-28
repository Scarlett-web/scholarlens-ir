"""Optional CJK search paths for new generations; old indexes remain readable."""
import re


def has_cjk(value: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff\uf900-\ufaff\U00020000-\U0002fa1f]", value))


def canonical_highlights(values: dict) -> dict:
    result = {}
    for field, fragments in values.items():
        key = field.removesuffix(".cjk")
        result.setdefault(key, [])
        result[key].extend(text for text in fragments if text not in result[key])
    return result
