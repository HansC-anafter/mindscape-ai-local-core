"""Deterministic JSON and hashing helpers for projection identities."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def stable_projection_id(*parts: str) -> str:
    normalized = [str(part or "").strip() for part in parts]
    if not normalized or any(not part for part in normalized):
        raise ValueError("knowledge_projection_identity_parts_required")
    return canonical_sha256(normalized)
