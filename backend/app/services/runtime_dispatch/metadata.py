"""Read-only runtime dispatch target and selector metadata."""

from __future__ import annotations

from typing import Any

from backend.app.services.host_resources.manager import list_host_resource_lanes
from backend.app.services.host_resources.queue_utilization import (
    get_latest_queue_utilization_snapshot,
)

from .feature_gate import get_runtime_dispatch_feature_gate


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _clean_int(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def list_runtime_dispatch_selector_types() -> dict[str, Any]:
    return {
        "feature_gate": get_runtime_dispatch_feature_gate(),
        "selector_types": [
            {
                "selector_type": "explicit_object_refs",
                "label": "Explicit object references",
                "workspace_scope_required": True,
                "max_items": 500,
                "input_shape": {
                    "object_refs": "string[]",
                },
                "supports_preview": True,
                "supports_apply": True,
            },
            {
                "selector_type": "task_query",
                "label": "Bounded task query",
                "workspace_scope_required": True,
                "max_items": 500,
                "input_shape": {
                    "status": "pending",
                    "capability_scope": "string",
                    "created_after": "iso8601",
                    "limit": "number",
                },
                "supports_preview": True,
                "supports_apply": True,
            },
        ],
        "limits": {
            "max_items": 500,
            "requires_workspace_access": True,
            "allows_cross_workspace_refs": False,
        },
    }


def _capacity_summary_for_lane(
    lane: dict[str, Any],
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    queue_shard = _clean_string(lane.get("queue_shard"))
    if not queue_shard:
        return {
            "queue_shard": None,
            "source": _clean_string(snapshot.get("source")),
            "available": False,
        }

    capacity_by_queue = _as_dict(snapshot.get("capacity_by_queue_shard"))
    queue_depths = _as_dict(snapshot.get("queue_depths"))
    utilization = _as_dict(snapshot.get("utilization_ratio_by_queue_shard"))
    capacity = _as_dict(capacity_by_queue.get(queue_shard))
    depth = _as_dict(queue_depths.get(queue_shard))
    return {
        "queue_shard": queue_shard,
        "source": _clean_string(snapshot.get("source")),
        "available": bool(capacity or depth),
        "active_runner_count": _clean_int(capacity.get("active_runner_count")),
        "claimable_runner_count": _clean_int(capacity.get("claimable_runner_count")),
        "available_slots_total": _clean_int(capacity.get("available_slots_total")),
        "max_inflight_total": _clean_int(capacity.get("max_inflight_total")),
        "pending": _clean_int(depth.get("pending")),
        "processing": _clean_int(depth.get("processing")),
        "utilization_ratio": utilization.get(queue_shard),
    }


def _target_from_lane(
    lane: dict[str, Any],
    *,
    workspace_id: str,
    utilization_snapshot: dict[str, Any],
) -> dict[str, Any]:
    lane_workspace_id = _clean_string(lane.get("workspace_id"))
    state = _clean_string(lane.get("state")) or "available"
    workspace_eligible = lane_workspace_id is None or lane_workspace_id == workspace_id
    state_eligible = state not in {"paused", "degraded", "critical", "disabled"}
    assignable = bool(workspace_eligible and state_eligible)
    reason = None
    if not workspace_eligible:
        reason = "workspace_mismatch"
    elif not state_eligible:
        reason = f"lane_state_{state}"

    return {
        "target_id": lane.get("lane_id"),
        "lane_id": lane.get("lane_id"),
        "label": lane.get("label") or lane.get("lane_id"),
        "workspace_id": lane_workspace_id,
        "capability_scope": lane.get("capability_scope"),
        "kind": lane.get("kind"),
        "queue_shard": lane.get("queue_shard"),
        "runner_profile": lane.get("runner_profile"),
        "resource_class": lane.get("resource_class"),
        "priority_class": lane.get("priority_class"),
        "resource_flavor": lane.get("resource_flavor"),
        "state": state,
        "max_concurrency": _clean_int(lane.get("max_concurrency")),
        "desired_worker_count": _clean_int(lane.get("desired_worker_count")),
        "model_profile": _as_dict(lane.get("model_profile")),
        "requirements": _as_dict(lane.get("requirements")),
        "metadata": _as_dict(lane.get("metadata")),
        "assignable": assignable,
        "assignability_reason": reason,
        "capacity_summary": _capacity_summary_for_lane(lane, utilization_snapshot),
    }


def list_runtime_dispatch_targets(workspace_id: str) -> dict[str, Any]:
    utilization_snapshot = get_latest_queue_utilization_snapshot()
    targets = []
    for lane in list_host_resource_lanes():
        if not isinstance(lane, dict):
            continue
        lane_workspace_id = _clean_string(lane.get("workspace_id"))
        if lane_workspace_id is not None and lane_workspace_id != workspace_id:
            continue
        targets.append(
            _target_from_lane(
                lane,
                workspace_id=workspace_id,
                utilization_snapshot=utilization_snapshot,
            )
        )
    targets.sort(key=lambda item: str(item.get("label") or item.get("lane_id") or ""))
    return {
        "feature_gate": get_runtime_dispatch_feature_gate(),
        "workspace_id": workspace_id,
        "targets": targets,
        "count": len(targets),
        "metadata_source": "host_resources_lane_registry",
        "queue_utilization_source": _clean_string(utilization_snapshot.get("source")),
        "degraded": bool(utilization_snapshot.get("degraded")),
        "errors": utilization_snapshot.get("errors")
        if isinstance(utilization_snapshot.get("errors"), list)
        else [],
    }
