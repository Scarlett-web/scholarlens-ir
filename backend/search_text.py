"""Optional CJK search paths for new generations; old indexes remain readable."""
import re

HIGHLIGHT_STOP_WORDS = frozenset(
    "a an and are as at be by for from in is it of on or that the this to was were with".split()
)


def highlight_query_text(query: str, *, phrase: bool = False) -> str:
    """Keep retrieval unchanged; avoid highlighting connective words in long queries."""
    if phrase:
        return query
    terms = query.split()
    meaningful = [term for term in terms if term.strip("\"'.,:;!?()").casefold() not in HIGHLIGHT_STOP_WORDS]
    return " ".join(meaningful) if meaningful else query


def has_cjk(value: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff\uf900-\ufaff\U00020000-\U0002fa1f]", value))


def canonical_highlights(values: dict) -> dict:
    result = {}
    for field, fragments in values.items():
        key = field.removesuffix(".cjk")
        result.setdefault(key, [])
        result[key].extend(text for text in fragments if text not in result[key])
    return result
