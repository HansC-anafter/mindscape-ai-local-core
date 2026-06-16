"""
Stored model route slot normalization and drift comparison helpers.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Sequence


def normalize_stored_slots(
    stored_slots: Sequence[Any],
    *,
    pack_id: str,
    owner_name: str,
    installed: bool,
    enabled: bool,
) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for index, slot in enumerate(stored_slots):
        if not isinstance(slot, dict):
            continue
        normalized.append(
            {
                "slot_id": str(slot.get("slot_id") or f"{pack_id}:stored:{index}"),
                "owner_kind": str(slot.get("owner_kind") or "pack"),
                "owner_id": str(slot.get("owner_id") or pack_id),
                "owner_name": str(slot.get("owner_name") or owner_name),
                "slot_kind": str(slot.get("slot_kind") or "stored_slot"),
                "title": str(
                    slot.get("title") or slot.get("slot_kind") or "stored_slot"
                ),
                "summary": str(slot.get("summary") or ""),
                "route_family": str(slot.get("route_family") or "stored_slot"),
                "source": str(
                    slot.get("source") or "installed_packs.metadata.model_route_slots"
                ),
                "settings_anchor": str(
                    slot.get("settings_anchor") or "basic:model-routing-registry"
                ),
                "installed": slot.get("installed", installed),
                "enabled": slot.get("enabled", enabled),
                "evidence_path": slot.get("evidence_path"),
                "raw": dict(slot.get("raw") or {}),
            }
        )
    return normalized


def coerce_slot_count(value: Any, *, fallback: int) -> int:
    try:
        if value is None:
            return fallback
        return int(value)
    except (TypeError, ValueError):
        return fallback


def canonicalize_slots(slots: Sequence[Dict[str, Any]]) -> List[str]:
    canonical: List[str] = []
    for slot in slots:
        if not isinstance(slot, dict):
            continue
        canonical.append(
            json.dumps(slot, sort_keys=True, ensure_ascii=False, default=str)
        )
    return sorted(canonical)


def pack_slot_registration_changed(
    *,
    stored_slots: Sequence[Dict[str, Any]],
    stored_slot_count: Any,
    live_slots: Sequence[Dict[str, Any]],
) -> bool:
    normalized_stored_slots = canonicalize_slots(stored_slots)
    normalized_live_slots = canonicalize_slots(live_slots)
    normalized_stored_count = coerce_slot_count(
        stored_slot_count,
        fallback=len(normalized_stored_slots),
    )
    if normalized_stored_count != len(normalized_live_slots):
        return True
    return normalized_stored_slots != normalized_live_slots
