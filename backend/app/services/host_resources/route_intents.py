"""Route intent preview for host resource scheduling."""

from __future__ import annotations

import asyncio
from typing import Any

from backend.app.dependencies.auth import AuthContext
from backend.app.services.resource_governance import (
    build_resource_governance_context,
    require_workspace_resource_access,
)

from .lane_registry import get_lane
from .manager import get_cached_snapshot_or_degraded, get_host_resource_snapshot
from .queue_preview import build_route_reservation_candidate_previews
from .workspace_allocations import workspace_allocation_decision


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _lane_config(lane_id: str | None) -> dict[str, Any] | None:
    lane = get_lane(lane_id)
    return dict(lane) if isinstance(lane, dict) else None


def _lane_requirements(lane: dict[str, Any] | None) -> dict[str, Any]:
    if not lane:
        return {}
    requirements = lane.get("requirements") if isinstance(lane, dict) else {}
    return dict(requirements) if isinstance(requirements, dict) else {}


def _route_request_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    route_request = payload.get("route_request") if isinstance(payload, dict) else None
    raw = dict(route_request) if isinstance(route_request, dict) else dict(payload or {})
    target_lane = raw.get("target_lane") or raw.get("lane_id")
    if target_lane:
        raw["target_lane"] = str(target_lane)
    raw.setdefault("priority_class", "default")
    raw.setdefault("drain_policy", "drain_after_current")
    raw.setdefault("preemption_policy", "never")
    raw.setdefault("resume_policy", "auto_restore_previous")
    raw.setdefault("requested_by", "route_intent_preview")
    return raw


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _allocation_preview_decision(
    *,
    payload: dict[str, Any],
    route_request: dict[str, Any],
    auth_context: AuthContext | None,
) -> dict[str, Any]:
    if auth_context is None:
        return {"accepted": True, "reason": "compatibility_no_auth_context"}
    workspace_id = _clean_string(
        route_request.get("workspace_id") or payload.get("workspace_id")
    )
    allocation_id = _clean_string(
        route_request.get("workspace_allocation_id")
        or route_request.get("allocation_id")
        or payload.get("workspace_allocation_id")
        or payload.get("allocation_id")
    )
    governance_context = build_resource_governance_context(
        auth_context,
        workspace_id=workspace_id,
    )
    if governance_context.get("is_global_admin") and not workspace_id:
        return {
            "accepted": True,
            "reason": "global_admin_allocation_bypass",
            "governance_context": governance_context,
        }
    workspace_id = require_workspace_resource_access(auth_context, workspace_id)
    decision = workspace_allocation_decision(
        workspace_id=workspace_id,
        lane_id=_clean_string(route_request.get("target_lane")),
        allocation_id=allocation_id,
    )
    if decision.get("accepted"):
        route_request["workspace_id"] = workspace_id
        allocation = decision.get("allocation") if isinstance(decision.get("allocation"), dict) else {}
        route_request["workspace_allocation_id"] = allocation.get("allocation_id")
    return {
        **decision,
        "governance_context": governance_context,
    }


async def build_route_intent_preview(
    payload: dict[str, Any] | None = None,
    *,
    auth_context: AuthContext | None = None,
) -> dict[str, Any]:
    payload = payload or {}
    route_request = _route_request_from_payload(payload or {})
    target_lane = str(route_request.get("target_lane") or "").strip() or None
    lane = _lane_config(target_lane)
    if target_lane and lane is None:
        return {
            "route_intent": route_request,
            "route_intent_preview": {
                "target_lane": target_lane,
                "decision": "unknown_lane",
                "reason": "target_lane_not_declared",
                "resource_flavor": route_request.get("resource_flavor"),
                "resource_groups": route_request.get("resource_groups") or [],
                "estimated_memory_mb": 0,
                "pressure_delta": {
                    "estimated_memory_mb": 0,
                    "headroom_before_mb": 0,
                    "headroom_after_mb": 0,
                },
                "matching_candidates": [],
                "preview_errors": [],
                "held_candidates": [],
                "non_destructive_action_plan": [],
                "reservation_payload": None,
            },
        }
    requirements = _lane_requirements(lane)
    if not route_request.get("resource_groups"):
        route_request["resource_groups"] = _string_list(requirements.get("exclusive_groups"))
    lane_resource_flavor = (lane or {}).get("resource_flavor") or requirements.get("resource_flavor")
    if not route_request.get("resource_flavor") and lane_resource_flavor:
        route_request["resource_flavor"] = lane_resource_flavor
    allocation_decision = _allocation_preview_decision(
        payload=payload,
        route_request=route_request,
        auth_context=auth_context,
    )

    preview_errors: list[dict[str, Any]] = []
    if payload.get("refresh"):
        snapshot_timeout_seconds = float(payload.get("snapshot_timeout_seconds") or 1.0)
        try:
            snapshot = await asyncio.wait_for(
                get_host_resource_snapshot(refresh=True),
                timeout=max(0.25, min(snapshot_timeout_seconds, 5.0)),
            )
        except Exception as exc:
            snapshot = get_cached_snapshot_or_degraded()
            preview_errors.append(
                {
                    "source": "host_snapshot",
                    "error": type(exc).__name__ or str(exc),
                }
            )
    else:
        snapshot = get_cached_snapshot_or_degraded()
    capacity = snapshot.get("capacity") if isinstance(snapshot.get("capacity"), dict) else {}
    memory_mb = requirements.get("memory_mb")
    try:
        estimated_memory_mb = int(memory_mb or 0)
    except Exception:
        estimated_memory_mb = 0
    headroom_mb = int(capacity.get("memory_mb") or 0)
    pressure_delta = {
        "estimated_memory_mb": estimated_memory_mb,
        "headroom_before_mb": headroom_mb,
        "headroom_after_mb": max(0, headroom_mb - estimated_memory_mb),
    }
    reservation = {
        "reservation_id": "preview",
        "state": "reserved_waiting",
        "route_request": route_request,
    }
    previews: dict[str, Any] = {}
    timeout_seconds = float(payload.get("candidate_preview_timeout_seconds") or 1.0)
    if payload.get("include_candidates"):
        try:
            previews = await asyncio.wait_for(
                build_route_reservation_candidate_previews(
                    [reservation],
                    scan_limit=int(payload.get("scan_limit") or 25),
                ),
                timeout=max(0.25, min(timeout_seconds, 5.0)),
            )
        except Exception as exc:
            previews = {}
            preview_errors.append(
                {
                    "source": "candidate_preview",
                    "error": type(exc).__name__ or str(exc),
                }
            )
    candidate_preview = previews.get("preview") or {}
    return {
        "route_intent": route_request,
        "route_intent_preview": {
            "target_lane": target_lane,
            "decision": "preview_ready",
            "reason": None,
            "workspace_allocation_decision": allocation_decision,
            "resource_flavor": route_request.get("resource_flavor"),
            "resource_groups": route_request.get("resource_groups") or [],
            "estimated_memory_mb": estimated_memory_mb,
            "pressure_delta": pressure_delta,
            "matching_candidates": candidate_preview.get("matching_candidates") or [],
            "preview_errors": preview_errors,
            "held_candidates": [],
            "non_destructive_action_plan": [
                {
                    "action": "drain_after_current",
                    "target": target_lane,
                    "preemption_policy": route_request.get("preemption_policy"),
                }
            ],
            "reservation_payload": {
                "route_request": route_request,
            },
        },
    }
