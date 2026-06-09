"""Reconcile desired host-resource worker targets with live managed runtime workers."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from .dynamic_lane_store import HostResourceDynamicLaneStore, update_dynamic_lane
from .host_bridge import HostBridgeError, call_host_resource_lane_workers_set
from .worker_target_resolution import resolve_worker_target

logger = logging.getLogger(__name__)


def _clean_string(value: Any) -> str:
    return str(value or "").strip()


def _clean_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _desired_worker_count(lane: dict[str, Any]) -> int:
    return max(0, _clean_int(lane.get("desired_worker_count"), default=0))


def _lane_uses_managed_mlx_worker(lane: dict[str, Any]) -> bool:
    if _desired_worker_count(lane) <= 0:
        return False
    if _clean_string(lane.get("resource_flavor")) != "local.mlx.vision":
        return False
    model_profile = _dict(lane.get("model_profile"))
    metadata = _dict(lane.get("metadata"))
    adapter_id = _clean_string(
        model_profile.get("adapter_id")
        or metadata.get("adapter_id")
        or metadata.get("runtime_adapter_id")
    )
    return adapter_id == "apple_mlx_vlm"


def _lane_state_from_reconcile_result(result: dict[str, Any]) -> str:
    if not bool(result.get("accepted") or result.get("success")):
        return "degraded"
    reason = _clean_string(result.get("reason"))
    if reason in {
        "worker_target_already_running",
        "worker_target_port_already_listening",
    }:
        return "available"
    return "starting"


async def reconcile_desired_worker_targets(
    *,
    lane_id: str | None = None,
) -> dict[str, Any]:
    """Ensure every desired managed MLX lane has a live worker target."""

    requested_lane_id = _clean_string(lane_id) or None
    lanes = HostResourceDynamicLaneStore("core").list_lanes()
    summary: dict[str, Any] = {
        "requested_lane_id": requested_lane_id,
        "inspected": 0,
        "started": 0,
        "already_running": 0,
        "degraded": 0,
        "skipped": 0,
        "lanes": [],
    }

    for lane in lanes:
        current_lane_id = _clean_string(lane.get("lane_id"))
        if requested_lane_id and current_lane_id != requested_lane_id:
            continue
        if not _lane_uses_managed_mlx_worker(lane):
            summary["skipped"] += 1
            continue

        summary["inspected"] += 1
        desired = _desired_worker_count(lane)
        resolution = resolve_worker_target(lane, desired)
        if not resolution.get("accepted"):
            update_dynamic_lane(current_lane_id, {"state": "degraded"})
            summary["degraded"] += 1
            summary["lanes"].append(
                {
                    "lane_id": current_lane_id,
                    "accepted": False,
                    "reason": resolution.get("reason") or "worker_target_resolution_failed",
                    "state": "degraded",
                    "resolution": resolution,
                }
            )
            continue

        arguments = {
            "lane_id": current_lane_id,
            "desired_worker_count": desired,
            "queue_shard": lane.get("queue_shard"),
            "runner_profile": lane.get("runner_profile"),
            "resource_class": lane.get("resource_class"),
            "worker_env": resolution.get("worker_env") or {},
        }

        try:
            result = await call_host_resource_lane_workers_set(arguments)
        except HostBridgeError as exc:
            update_dynamic_lane(current_lane_id, {"state": "degraded"})
            summary["degraded"] += 1
            summary["lanes"].append(
                {
                    "lane_id": current_lane_id,
                    "accepted": False,
                    "reason": "host_bridge_worker_target_failed",
                    "state": "degraded",
                    "error": str(exc),
                    "resolution": resolution,
                }
            )
            continue

        state = _lane_state_from_reconcile_result(result)
        update_dynamic_lane(current_lane_id, {"state": state})
        reason = _clean_string(result.get("reason"))
        if reason == "worker_target_started":
            summary["started"] += 1
        elif reason in {
            "worker_target_already_running",
            "worker_target_port_already_listening",
        }:
            summary["already_running"] += 1
        elif state == "degraded":
            summary["degraded"] += 1

        summary["lanes"].append(
            {
                "lane_id": current_lane_id,
                "accepted": bool(result.get("accepted") or result.get("success")),
                "reason": reason or "worker_target_reconciled",
                "state": state,
                "host_bridge_result": result,
                "resolution": resolution,
            }
        )

    return summary


async def run_worker_target_reconcile_loop() -> None:
    """Keep desired managed MLX worker targets present after runtime exits."""

    startup_delay_seconds = max(
        0,
        _clean_int(
            os.getenv("LOCAL_CORE_HOST_RESOURCE_WORKER_RECONCILE_STARTUP_DELAY_SECONDS"),
            default=5,
        ),
    )
    interval_seconds = max(
        5,
        _clean_int(
            os.getenv("LOCAL_CORE_HOST_RESOURCE_WORKER_RECONCILE_INTERVAL_SECONDS"),
            default=15,
        ),
    )

    if startup_delay_seconds > 0:
        await asyncio.sleep(startup_delay_seconds)

    while True:
        try:
            summary = await reconcile_desired_worker_targets()
            if summary.get("inspected", 0) > 0:
                logger.info(
                    "Host resource worker target reconcile: inspected=%d started=%d already_running=%d degraded=%d",
                    summary.get("inspected", 0),
                    summary.get("started", 0),
                    summary.get("already_running", 0),
                    summary.get("degraded", 0),
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "Host resource worker target reconcile failed: %s",
                exc,
                exc_info=True,
            )
        await asyncio.sleep(interval_seconds)
