"""Host bridge worker target control for dynamic lanes."""

from __future__ import annotations

from typing import Any

from backend.app.dependencies.auth import AuthContext
from backend.app.runner.db_pool_pressure import sample_pgbouncer_pressure
from backend.app.services.resource_governance import (
    build_resource_governance_context,
    require_workspace_resource_access,
)

from .dynamic_lane_store import get_dynamic_lane, update_dynamic_lane
from .host_bridge import HostBridgeError, call_host_resource_lane_workers_set
from .manager import get_host_resource_snapshot, list_active_route_reservations
from .summary import build_host_resource_summary
from .workspace_allocations import workspace_allocation_decision
from .worker_target_resolution import (
    accepted_capability_codes_for_lane,
    resolve_worker_target,
    runner_max_inflight_for_lane,
)


def _clean_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _worker_env_for_lane(lane: dict[str, Any]) -> dict[str, Any]:
    model_profile = lane.get("model_profile") if isinstance(lane.get("model_profile"), dict) else {}
    port = _clean_int(model_profile.get("port"), default=8211)
    env = {
        "MLX_PORT": port,
        "LOCAL_CORE_RUNNER_PROFILE": lane.get("runner_profile"),
        "LOCAL_CORE_RUNNER_ACCEPTED_PARTITIONS": lane.get("queue_shard"),
        "LOCAL_CORE_RUNNER_ACCEPTED_RESOURCE_CLASSES": lane.get("resource_class"),
        "LOCAL_CORE_RUNNER_ACCEPTED_CAPABILITY_CODES": accepted_capability_codes_for_lane(lane),
        "LOCAL_CORE_RUNNER_MAX_INFLIGHT": runner_max_inflight_for_lane(lane),
        "LOCAL_CORE_RUNNER_DISPATCH_MODE": "docker_local",
        "LOCAL_CORE_HOST_RESOURCE_LANE_ID": lane.get("lane_id"),
    }
    model = model_profile.get("model")
    if model:
        env["MLX_MODEL"] = model
    return env


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _lane_state_for_worker_result(*, desired: int, result: dict[str, Any]) -> str:
    if desired <= 0:
        return "offline"
    reason = _clean_string(result.get("reason"))
    if reason in {"worker_target_already_running", "worker_target_port_already_listening"}:
        return "available"
    return "starting"


def _workspace_quota_decision(
    *,
    lane_id: str,
    desired: int,
    auth_context: AuthContext | None,
    workspace_id: str | None,
    allocation_id: str | None,
) -> dict[str, Any]:
    if auth_context is None or desired <= 0:
        return {"accepted": True, "reason": "workspace_quota_not_required"}
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
    normalized_workspace_id = require_workspace_resource_access(
        auth_context,
        workspace_id,
    )
    decision = workspace_allocation_decision(
        workspace_id=normalized_workspace_id,
        lane_id=lane_id,
        allocation_id=allocation_id,
    )
    if not decision.get("accepted"):
        return {
            **decision,
            "governance_context": governance_context,
        }
    allocation = decision.get("allocation") if isinstance(decision.get("allocation"), dict) else {}
    max_worker_target = max(0, _clean_int(allocation.get("max_worker_target"), default=0))
    if desired > max_worker_target:
        return {
            "accepted": False,
            "reason": "desired_worker_count_exceeds_workspace_allocation",
            "desired_worker_count": desired,
            "max_worker_target": max_worker_target,
            "allocation": allocation,
            "governance_context": governance_context,
        }
    return {
        **decision,
        "governance_context": governance_context,
    }


async def _resource_gate_allows_start() -> tuple[bool, dict[str, Any]]:
    db_pressure = sample_pgbouncer_pressure()
    if db_pressure.paused:
        return False, {
            "reason": db_pressure.reason,
            "db_pool_pressure": {
                "state": db_pressure.state,
                "reason": db_pressure.reason,
                "pools": db_pressure.pools,
            },
        }

    snapshot = await get_host_resource_snapshot(refresh=False)
    summary = build_host_resource_summary(
        snapshot,
        active_reservations=list_active_route_reservations(),
    )
    if summary.get("pressure_state") not in {"ok", "unknown"}:
        return False, {
            "reason": "host_resource_pressure_not_ok",
            "summary": summary,
        }
    return True, {
        "reason": "resource_gate_open",
        "summary": {
            "pressure_state": summary.get("pressure_state"),
            "free_percent": summary.get("free_percent"),
            "route_controls": summary.get("route_controls"),
        },
        "db_pool_pressure": {
            "state": db_pressure.state,
            "reason": db_pressure.reason,
            "pools": db_pressure.pools,
        },
    }


async def set_lane_worker_target(
    lane_id: str,
    desired_worker_count: int,
    *,
    auth_context: AuthContext | None = None,
    workspace_id: str | None = None,
    allocation_id: str | None = None,
) -> dict[str, Any]:
    lane = get_dynamic_lane(lane_id)
    if not lane:
        return {
            "accepted": False,
            "lane_id": lane_id,
            "desired_worker_count": desired_worker_count,
            "reason": "dynamic_lane_not_found",
        }

    desired = max(0, _clean_int(desired_worker_count, default=0))
    max_concurrency = max(1, _clean_int(lane.get("max_concurrency"), default=1))
    if desired > max_concurrency:
        return {
            "accepted": False,
            "lane_id": lane_id,
            "desired_worker_count": desired,
            "max_concurrency": max_concurrency,
            "reason": "desired_worker_count_exceeds_max_concurrency",
        }
    quota_decision = _workspace_quota_decision(
        lane_id=lane_id,
        desired=desired,
        auth_context=auth_context,
        workspace_id=_clean_string(workspace_id),
        allocation_id=_clean_string(allocation_id),
    )
    if not quota_decision.get("accepted"):
        return {
            "accepted": False,
            "lane_id": lane_id,
            "desired_worker_count": desired,
            "max_concurrency": max_concurrency,
            "reason": quota_decision.get("reason") or "workspace_quota_blocked",
            "workspace_quota": quota_decision,
            "lane": lane,
        }

    resolution: dict[str, Any] = {"reason": "stop_target_does_not_require_runtime_slot"}
    if desired > 0:
        resolution = resolve_worker_target(lane, desired)
        if not resolution.get("accepted"):
            return {
                "accepted": False,
                "lane_id": lane_id,
                "desired_worker_count": desired,
                "max_concurrency": max_concurrency,
                "reason": resolution.get("reason") or "worker_target_resolution_failed",
                "resolution": resolution,
                "lane": lane,
            }
        gate_open, gate = await _resource_gate_allows_start()
        if not gate_open:
            return {
                "accepted": False,
                "lane_id": lane_id,
                "desired_worker_count": desired,
                "max_concurrency": max_concurrency,
                "reason": gate.get("reason") or "resource_gate_blocked",
                "gate": gate,
                "lane": lane,
            }
    else:
        gate = {"reason": "stop_target_does_not_require_resource_gate"}

    arguments = {
        "lane_id": lane_id,
        "desired_worker_count": desired,
        "queue_shard": lane.get("queue_shard"),
        "runner_profile": lane.get("runner_profile"),
        "resource_class": lane.get("resource_class"),
        "worker_env": resolution.get("worker_env") or _worker_env_for_lane(lane),
    }
    try:
        result = await call_host_resource_lane_workers_set(arguments)
    except HostBridgeError as exc:
        return {
            "accepted": False,
            "lane_id": lane_id,
            "desired_worker_count": desired,
            "max_concurrency": max_concurrency,
            "reason": "host_bridge_worker_target_failed",
            "error": str(exc),
            "gate": gate,
            "lane": lane,
        }

    accepted = bool(result.get("accepted") or result.get("success"))
    persisted_lane = lane
    if desired > 0 and accepted:
        persisted_lane = update_dynamic_lane(
            lane_id,
            {
                "desired_worker_count": desired,
                "state": _lane_state_for_worker_result(desired=desired, result=result),
            },
        ) or lane
    elif desired <= 0:
        persisted_lane = update_dynamic_lane(
            lane_id,
            {
                "desired_worker_count": desired,
                "state": "offline" if accepted else "degraded",
            },
        ) or lane
    return {
        "accepted": accepted,
        "lane_id": lane_id,
        "desired_worker_count": desired,
        "max_concurrency": max_concurrency,
        "reason": result.get("reason") if not accepted else "worker_target_accepted",
        "host_bridge_result": result,
        "gate": gate,
        "workspace_quota": quota_decision,
        "resolution": resolution,
        "lane": persisted_lane,
    }
