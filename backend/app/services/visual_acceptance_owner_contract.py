"""
Explicit owner metadata helpers for visual acceptance bundles.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

OWNER_CAPABILITY_METADATA_KEYS = (
    "owning_capability_code",
    "review_workbench_capability_code",
)


def normalize_owner_capability_code(value: Any) -> Optional[str]:
    normalized = str(value or "").strip()
    return normalized or None


def resolve_explicit_owner_capability_code(
    context_metadata: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    metadata = dict(context_metadata or {})
    for key in OWNER_CAPABILITY_METADATA_KEYS:
        value = normalize_owner_capability_code(metadata.get(key))
        if value:
            return value
    return None
