"""Deterministic projection row identities."""

from __future__ import annotations

import hashlib
from typing import Iterable


def stable_projection_id(prefix: str, parts: Iterable[str]) -> str:
    normalized = tuple(str(part).strip() for part in parts)
    if any(not item for item in normalized):
        raise ValueError(f"knowledge_projection_{prefix}_identity_part_required")
    digest = hashlib.sha256("\x1f".join(normalized).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest}"


__all__ = ["stable_projection_id"]
