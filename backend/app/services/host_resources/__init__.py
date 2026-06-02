"""Host resource control-plane helpers."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_ADVISOR_EXPORTS = {
    "HostResourceAdvice",
    "evaluate_runner_requirements",
}

_MANAGER_EXPORTS = {
    "cancel_route_reservation",
    "create_route_reservation",
    "get_host_resource_snapshot",
    "get_runner_claim_gate",
    "list_active_route_reservations",
    "list_host_resource_lanes",
    "pause_runner_claim_gate",
    "resume_lane",
    "resume_runner_claim_gate",
    "pause_lane",
}

_DYNAMIC_LANE_EXPORTS = {
    "create_dynamic_lane",
    "get_dynamic_lane",
    "list_dynamic_lanes",
    "list_dynamic_queue_shards",
    "update_dynamic_lane",
}

_SUBMODULE_EXPORTS = {
    "lane_registry",
    "manager",
    "queue_utilization",
    "route_gate",
    "route_identity_projection",
    "schema_readiness",
}


def __getattr__(name: str) -> Any:
    if name in _ADVISOR_EXPORTS:
        return getattr(import_module(f"{__name__}.advisor"), name)
    if name in _MANAGER_EXPORTS:
        return getattr(import_module(f"{__name__}.manager"), name)
    if name in _DYNAMIC_LANE_EXPORTS:
        return getattr(import_module(f"{__name__}.dynamic_lane_store"), name)
    if name in _SUBMODULE_EXPORTS:
        return import_module(f"{__name__}.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "HostResourceAdvice",
    "cancel_route_reservation",
    "create_route_reservation",
    "evaluate_runner_requirements",
    "get_host_resource_snapshot",
    "get_runner_claim_gate",
    "create_dynamic_lane",
    "get_dynamic_lane",
    "list_dynamic_lanes",
    "list_dynamic_queue_shards",
    "list_active_route_reservations",
    "list_host_resource_lanes",
    "pause_lane",
    "pause_runner_claim_gate",
    "resume_lane",
    "resume_runner_claim_gate",
    "route_gate",
    "update_dynamic_lane",
]
