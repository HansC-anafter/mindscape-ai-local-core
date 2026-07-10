"""Pure resource lease key construction."""

from __future__ import annotations

import hashlib


LEASE_KEY_PREFIX = "mindscape:runner_resources:lease:v1"


def _normalize_key_part(value: str) -> str:
    normalized = "".join(
        char if char.isalnum() or char in {"-", "_", "."} else "_"
        for char in str(value or "").strip()
    ).strip("_")
    return normalized[:64] or "default"


def build_resource_lease_key(resource_type: str, resource_id: str) -> str:
    normalized_type = _normalize_key_part(resource_type)
    normalized_id = str(resource_id or "default").strip() or "default"
    digest = hashlib.sha256(normalized_id.encode("utf-8")).hexdigest()[:16]
    label = _normalize_key_part(normalized_id)
    return f"{LEASE_KEY_PREFIX}:{normalized_type}:{label}:{digest}"


__all__ = ["LEASE_KEY_PREFIX", "build_resource_lease_key"]
