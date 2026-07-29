"""Deterministic exact entity resolution; no hidden fuzzy merge."""

from __future__ import annotations

import re
import unicodedata


_SPACE = re.compile(r"\s+")


def canonical_entity_key(entity_type: str, value: str) -> str:
    normalized_type = _SPACE.sub(
        "_",
        unicodedata.normalize("NFKC", str(entity_type)).strip().casefold(),
    )
    normalized_value = _SPACE.sub(
        " ",
        unicodedata.normalize("NFKC", str(value)).strip().casefold(),
    )
    if not normalized_type or not normalized_value:
        raise ValueError("knowledge_graph_entity_identity_required")
    return f"{normalized_type}:{normalized_value}"


__all__ = ["canonical_entity_key"]
