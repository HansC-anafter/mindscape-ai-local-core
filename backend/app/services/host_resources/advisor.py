"""Host resource advisor for runner admission."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.services.runner_resources.requirements import ResourceRequirements

from .lane_registry import get_lane
from .manager import get_cached_snapshot_or_degraded, is_lane_paused


@dataclass(frozen=True)
class HostResourceAdvice:
    allow: bool
    decision: str
    reason: str | None
    payload: dict[str, Any]


def _lane_requirements(lane_id: str | None) -> dict[str, Any]:
    lane = get_lane(lane_id)
    if not lane:
        return {}
    requirements = lane.get("requirements")
    return dict(requirements) if isinstance(requirements, dict) else {}


def _requirement_memory(requirements: dict[str, Any], fallback: int = 0) -> int | None:
    value = requirements.get("memory_mb")
    if value is None:
        if requirements.get("memory_source") == "unknown":
            return None
        return fallback
    try:
        return max(0, int(value))
    except Exception:
        return fallback


def _exclusive_groups(requirements: dict[str, Any]) -> set[str]:
    groups = requirements.get("exclusive_groups")
    if not isinstance(groups, list):
        return set()
    return {str(group) for group in groups if str(group).strip()}


def _active_blocking_consumers(snapshot: dict[str, Any], groups: set[str]) -> list[str]:
    if not groups:
        return []
    consumers = snapshot.get("consumers")
    if not isinstance(consumers, list):
        return []
    blocked: list[str] = []
    for consumer in consumers:
        if not isinstance(consumer, dict):
            continue
        consumer_groups = {
            str(group)
            for group in consumer.get("exclusive_groups", [])
            if str(group).strip()
        }
        if groups.intersection(consumer_groups):
            blocked.append(str(consumer.get("consumer_id") or consumer.get("label") or "consumer"))
    return blocked


def _preview_from_snapshot(
    *,
    snapshot: dict[str, Any],
    lane_id: str | None,
    requirements: dict[str, Any],
) -> HostResourceAdvice:
    required_memory = _requirement_memory(requirements)
    required_cpu = int(requirements.get("cpu_weight") or 1)
    groups = _exclusive_groups(requirements)
    available = snapshot.get("capacity") if isinstance(snapshot.get("capacity"), dict) else {}
    available_memory = int(available.get("memory_mb") or 0)
    blocking_consumers = _active_blocking_consumers(snapshot, groups)
    base_payload = {
        "lane_id": lane_id,
        "required": {
            "memory_mb": required_memory,
            "cpu_weight": required_cpu,
            "exclusive_groups": sorted(groups),
        },
        "available": {
            "memory_mb": available_memory,
            "cpu_weight": available.get("cpu_weight_tokens", 0),
        },
        "blocking_consumers": blocking_consumers,
        "snapshot_captured_at": snapshot.get("captured_at"),
    }

    if lane_id and is_lane_paused(lane_id):
        return HostResourceAdvice(False, "defer", "lane_paused", base_payload)
    if required_memory is None:
        return HostResourceAdvice(False, "unknown_requirements", "memory_requirement_unknown", base_payload)
    if snapshot.get("degraded") and required_memory > 0:
        return HostResourceAdvice(False, "manual_action_required", "host_telemetry_degraded", base_payload)
    if blocking_consumers:
        return HostResourceAdvice(False, "defer", "exclusive_group_busy", base_payload)
    if required_memory > available_memory:
        return HostResourceAdvice(False, "defer", "insufficient_memory_headroom", base_payload)
    return HostResourceAdvice(True, "allow", None, base_payload)


def evaluate_runner_requirements(requirements: ResourceRequirements) -> HostResourceAdvice:
    lane_id = requirements.vision_lane or requirements.llm_lane
    lane_requirements = _lane_requirements(lane_id)
    merged = dict(lane_requirements)
    if requirements.memory_mb > 0:
        merged["memory_mb"] = requirements.memory_mb
        merged["memory_source"] = "resource_requirements"
    if requirements.cpu_weight:
        merged["cpu_weight"] = requirements.cpu_weight

    if not lane_id and requirements.memory_mb <= 0:
        return HostResourceAdvice(True, "allow", None, {"lane_id": None})

    snapshot = get_cached_snapshot_or_degraded()
    return _preview_from_snapshot(
        snapshot=snapshot,
        lane_id=lane_id,
        requirements=merged,
    )
