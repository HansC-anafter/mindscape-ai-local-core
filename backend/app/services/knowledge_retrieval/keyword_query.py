"""Bounded lexical query derivatives for PostgreSQL text search."""

from __future__ import annotations

import re


_CJK_RUN = re.compile(
    r"[\u3400-\u4dbf\u4e00-\u9fff\U00020000-\U0002fa1f]+"
)
_CJK_PREFIX_WIDTH = 2
_CJK_PREFIX_LIMIT = 64


def cjk_prefix_tsquery(query: str) -> str:
    """Return safe, bounded CJK bigram prefix terms joined by OR."""

    terms: list[str] = []
    for match in _CJK_RUN.finditer(query):
        run = match.group(0)
        if len(run) < _CJK_PREFIX_WIDTH:
            continue
        for offset in range(len(run) - _CJK_PREFIX_WIDTH + 1):
            term = run[offset : offset + _CJK_PREFIX_WIDTH]
            if term in terms:
                continue
            terms.append(term)
            if len(terms) >= _CJK_PREFIX_LIMIT:
                return " | ".join(f"{item}:*" for item in terms)
    return " | ".join(f"{item}:*" for item in terms)


__all__ = ["cjk_prefix_tsquery"]
