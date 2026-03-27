"""
Shared follow-up contract helpers for visual acceptance review flows.
"""

from __future__ import annotations

from typing import Any, Dict

FOLLOWUP_ACTION_CAPABILITY_CONSUMER_HANDOFF = "capability_consumer_handoff"
FOLLOWUP_LANE_CAPABILITY_CONSUMER_HANDOFF = "capability_consumer_handoff"
FOLLOWUP_CONSUMER_CAPABILITY_OWNED = "capability_owned_consumer"
FOLLOWUP_PLAN_CAPABILITY_CONSUMER_HANDOFF_REQUESTED = (
    "capability_consumer_handoff_requested"
)
FOLLOWUP_PLAN_CAPABILITY_CONSUMER_HANDOFF_READY = (
    "capability_consumer_handoff_ready"
)

_LEGACY_ACTION_ALIAS_MAP = {
    "pack_consumer_handoff": FOLLOWUP_ACTION_CAPABILITY_CONSUMER_HANDOFF,
}
_LEGACY_LANE_ALIAS_MAP = {
    "pack_consumer_handoff": FOLLOWUP_LANE_CAPABILITY_CONSUMER_HANDOFF,
}
_LEGACY_CONSUMER_ALIAS_MAP = {
    "pack_owned_consumer": FOLLOWUP_CONSUMER_CAPABILITY_OWNED,
}
_LEGACY_PLAN_KEY_ALIAS_MAP = {
    "pack_consumer_handoff_requested": (
        FOLLOWUP_PLAN_CAPABILITY_CONSUMER_HANDOFF_REQUESTED
    ),
    "pack_consumer_handoff_ready": FOLLOWUP_PLAN_CAPABILITY_CONSUMER_HANDOFF_READY,
}


def normalize_followup_action_id(action_id: Any) -> str:
    normalized = str(action_id or "").strip()
    return _LEGACY_ACTION_ALIAS_MAP.get(normalized, normalized)


def normalize_followup_lane_id(lane_id: Any) -> str:
    normalized = str(lane_id or "").strip()
    return _LEGACY_LANE_ALIAS_MAP.get(normalized, normalized)


def normalize_followup_consumer_kind(consumer_kind: Any) -> str:
    normalized = str(consumer_kind or "").strip()
    return _LEGACY_CONSUMER_ALIAS_MAP.get(normalized, normalized)


def followup_plan_flag_value(followup_plan: Dict[str, Any], plan_key: str) -> bool:
    if not isinstance(followup_plan, dict):
        return False
    normalized_key = _LEGACY_PLAN_KEY_ALIAS_MAP.get(plan_key, plan_key)
    legacy_keys = [
        key
        for key, mapped_key in _LEGACY_PLAN_KEY_ALIAS_MAP.items()
        if mapped_key == normalized_key
    ]
    return bool(
        followup_plan.get(normalized_key)
        or any(followup_plan.get(legacy_key) for legacy_key in legacy_keys)
    )


def canonicalize_followup_plan_flags(
    followup_plan: Dict[str, Any],
) -> Dict[str, Any]:
    if not isinstance(followup_plan, dict):
        return {}
    canonical = dict(followup_plan)
    for plan_key in (
        FOLLOWUP_PLAN_CAPABILITY_CONSUMER_HANDOFF_REQUESTED,
        FOLLOWUP_PLAN_CAPABILITY_CONSUMER_HANDOFF_READY,
    ):
        canonical[plan_key] = followup_plan_flag_value(canonical, plan_key)
    return canonical
