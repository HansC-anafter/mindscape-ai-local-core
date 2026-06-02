"""Resource lane request helpers for object runtime handoffs."""

from __future__ import annotations

from typing import Any

from backend.app.services.host_resources.lane_registry import get_lane


def _clean_string(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _candidate_lane_id(*containers: dict[str, Any]) -> str | None:
    for container in containers:
        if not isinstance(container, dict):
            continue
        request = container.get("resource_lane_request")
        if isinstance(request, dict):
            lane_id = _clean_string(
                request.get("lane_id")
                or request.get("target_lane")
                or request.get("host_resource_lane_id")
            )
            if lane_id:
                return lane_id
        lane_id = _clean_string(
            container.get("host_resource_lane_id")
            or container.get("runtime_lane_id")
            or container.get("lane_id")
        )
        if lane_id:
            return lane_id
    return None


def build_resource_lane_request(
    *,
    workspace_id: str,
    aol_metadata: dict[str, Any],
    action_parameters: dict[str, Any],
) -> dict[str, Any] | None:
    """Build a route-gate-compatible resource lane request."""

    lane_id = _candidate_lane_id(action_parameters, aol_metadata)
    if not lane_id:
        return None
    lane = get_lane(lane_id)
    if not isinstance(lane, dict):
        return None

    requirements = lane.get("requirements") if isinstance(lane.get("requirements"), dict) else {}
    resource_groups = requirements.get("exclusive_groups")
    if not isinstance(resource_groups, list):
        resource_groups = []

    request = {
        "lane_id": lane_id,
        "target_lane": lane_id,
        "queue_shard": _clean_string(lane.get("queue_shard")),
        "runner_profile_hint": _clean_string(lane.get("runner_profile")),
        "priority_class": _clean_string(lane.get("priority_class")) or "default",
        "resource_groups": [
            item for item in (_clean_string(value) for value in resource_groups) if item
        ],
        "resource_flavor": _clean_string(lane.get("resource_flavor")),
        "workspace_id": _clean_string(workspace_id),
        "source": "aol_runtime_resource_routing",
    }
    return {key: value for key, value in request.items() if value not in (None, "", [])}
