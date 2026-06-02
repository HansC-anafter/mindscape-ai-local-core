"""Host bridge worker target control for dynamic lanes."""

from __future__ import annotations

from typing import Any

from backend.app.runner.db_pool_pressure import sample_pgbouncer_pressure

from .dynamic_lane_store import get_dynamic_lane, update_dynamic_lane
from .host_bridge import HostBridgeError, call_host_resource_lane_workers_set
from .manager import get_host_resource_snapshot, list_active_route_reservations
from .summary import build_host_resource_summary


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
        "LOCAL_CORE_RUNNER_ACCEPTED_CAPABILITY_CODES": "ig_analyze_pinned_reference",
        "LOCAL_CORE_RUNNER_MAX_INFLIGHT": 1,
        "LOCAL_CORE_RUNNER_RUNTIME_ID": f"mlx:{lane.get('lane_id')}",
    }
    model = model_profile.get("model")
    if model:
        env["MLX_MODEL"] = model
    return env


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

    updated_lane = update_dynamic_lane(
        lane_id,
        {"desired_worker_count": desired},
    ) or lane

    if desired > 0:
        gate_open, gate = await _resource_gate_allows_start()
        if not gate_open:
            return {
                "accepted": False,
                "lane_id": lane_id,
                "desired_worker_count": desired,
                "max_concurrency": max_concurrency,
                "reason": gate.get("reason") or "resource_gate_blocked",
                "gate": gate,
                "lane": updated_lane,
            }
    else:
        gate = {"reason": "stop_target_does_not_require_resource_gate"}

    arguments = {
        "lane_id": lane_id,
        "desired_worker_count": desired,
        "queue_shard": updated_lane.get("queue_shard"),
        "runner_profile": updated_lane.get("runner_profile"),
        "resource_class": updated_lane.get("resource_class"),
        "worker_env": _worker_env_for_lane(updated_lane),
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
            "lane": updated_lane,
        }

    accepted = bool(result.get("accepted") or result.get("success"))
    return {
        "accepted": accepted,
        "lane_id": lane_id,
        "desired_worker_count": desired,
        "max_concurrency": max_concurrency,
        "reason": result.get("reason") if not accepted else "worker_target_accepted",
        "host_bridge_result": result,
        "gate": gate,
        "lane": updated_lane,
    }
