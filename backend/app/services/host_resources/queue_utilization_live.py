"""Live Redis queue utilization snapshot assembly."""

from __future__ import annotations

import time
from typing import Any, Awaitable, Callable

from .queue_utilization_support import (
    _clamped_scan_limit,
    _iso_from_epoch,
    _normalize_task_id,
    _to_int,
)


def default_queue_stores(
    *,
    ready_queue_order: list[str],
    list_dynamic_queue_shards_func: Callable[[], list[str]],
    queue_store_cls: Callable[..., Any],
) -> list[Any]:
    queue_shards: list[str] = []
    for queue_shard in [*ready_queue_order, *list_dynamic_queue_shards_func()]:
        normalized = str(queue_shard or "").strip()
        if normalized and normalized not in queue_shards:
            queue_shards.append(normalized)
    return [queue_store_cls(pack_id=queue_shard) for queue_shard in queue_shards]


async def pending_task_ids(queue_store: Any, *, scan_limit: int) -> list[str]:
    client = await queue_store._get_client()
    if not client:
        return []
    raw_ids = await client.lrange(queue_store.q_pending, 0, max(0, scan_limit - 1))
    return [
        _normalize_task_id(raw).strip()
        for raw in raw_ids
        if _normalize_task_id(raw).strip()
    ]


async def queue_depths(queue_store: Any) -> dict[str, int]:
    client = await queue_store._get_client()
    if not client:
        return {
            "pending": 0,
            "processing": 0,
            "delayed": 0,
            "deadletter": 0,
        }
    pending = await client.llen(queue_store.q_pending)
    processing = await client.zcard(queue_store.q_processing)
    delayed = await client.zcard(queue_store.q_delayed)
    deadletter = await client.llen(queue_store.q_deadletter)
    return {
        "pending": _to_int(pending),
        "processing": _to_int(processing),
        "delayed": _to_int(delayed),
        "deadletter": _to_int(deadletter),
    }


def visible_lane_identity(projection: dict[str, Any]) -> tuple[str, str]:
    concurrency_key = str(projection.get("concurrency_key") or "").strip()
    if concurrency_key:
        return "concurrency_key", concurrency_key

    route_identity = projection.get("route_identity")
    if not isinstance(route_identity, dict):
        route_identity = {}

    lane_id = str(route_identity.get("lane_id") or "").strip()
    if lane_id:
        return "route_lane", lane_id

    groups = [
        str(group).strip()
        for group in route_identity.get("resource_groups") or []
        if str(group).strip()
    ]
    if groups:
        return "resource_groups", ",".join(sorted(groups))

    playbook_code = str(
        projection.get("playbook_code") or projection.get("pack_id") or ""
    ).strip()
    if playbook_code:
        return "playbook", playbook_code

    return "unknown", "unknown"


def visible_lanes(
    *,
    task_ids: list[str],
    projections: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    lanes: dict[str, dict[str, Any]] = {}
    for queue_position, task_id in enumerate(task_ids):
        projection = projections.get(task_id)
        if not projection:
            continue
        lane_type, lane_value = visible_lane_identity(projection)
        lane_key = f"{lane_type}:{lane_value}"
        lane = lanes.setdefault(
            lane_key,
            {
                "lane_key": lane_key,
                "lane_type": lane_type,
                "lane_value": lane_value,
                "count": 0,
                "first_queue_position": queue_position,
                "pack_ids": [],
                "example_task_ids": [],
            },
        )
        lane["count"] += 1
        pack_id = str(projection.get("pack_id") or "").strip()
        if pack_id and pack_id not in lane["pack_ids"]:
            lane["pack_ids"].append(pack_id)
        if len(lane["example_task_ids"]) < 3:
            lane["example_task_ids"].append(task_id)

    return sorted(
        lanes.values(),
        key=lambda lane: (
            _to_int(lane.get("first_queue_position")),
            str(lane.get("lane_key")),
        ),
    )


async def active_heartbeats(
    queue_stores: list[Any],
    *,
    list_active_runner_resource_heartbeats_func: Callable[
        [Any], Awaitable[list[dict[str, Any]]]
    ],
) -> list[dict[str, Any]]:
    for queue_store in queue_stores:
        try:
            heartbeats = await list_active_runner_resource_heartbeats_func(queue_store)
        except Exception:
            heartbeats = []
        if heartbeats:
            return heartbeats
    return []


def capacity_by_queue_shard(
    *,
    queue_names: list[str],
    heartbeats: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    capacity_by_queue = {
        queue_name: {
            "active_runner_count": 0,
            "claimable_runner_count": 0,
            "claim_blocked_runner_count": 0,
            "max_inflight_total": 0,
            "inflight_total": 0,
            "available_slots_total": 0,
            "claimable_available_slots_total": 0,
            "utilization_ratio": None,
            "runner_ids": [],
        }
        for queue_name in queue_names
    }

    for heartbeat in heartbeats:
        queue_shards = [
            str(item).strip()
            for item in heartbeat.get("queue_shards") or []
            if str(item).strip()
        ]
        capacity = heartbeat.get("capacity")
        if not isinstance(capacity, dict):
            capacity = {}
        claim_control = heartbeat.get("claim_control")
        if not isinstance(claim_control, dict):
            claim_control = {}
        claim_mode = str(claim_control.get("mode") or "active").strip().lower()
        claim_enabled = (
            claim_mode == "active" and claim_control.get("claim_enabled") is not False
        )
        for queue_shard in queue_shards:
            if queue_shard not in capacity_by_queue:
                capacity_by_queue[queue_shard] = {
                    "active_runner_count": 0,
                    "claimable_runner_count": 0,
                    "claim_blocked_runner_count": 0,
                    "max_inflight_total": 0,
                    "inflight_total": 0,
                    "available_slots_total": 0,
                    "claimable_available_slots_total": 0,
                    "utilization_ratio": None,
                    "runner_ids": [],
                }
            row = capacity_by_queue[queue_shard]
            row["active_runner_count"] += 1
            if claim_enabled:
                row["claimable_runner_count"] = (
                    _to_int(row.get("claimable_runner_count")) + 1
                )
            else:
                row["claim_blocked_runner_count"] = (
                    _to_int(row.get("claim_blocked_runner_count")) + 1
                )
            row["max_inflight_total"] += _to_int(capacity.get("max_inflight"))
            row["inflight_total"] += _to_int(capacity.get("inflight"))
            available_slots = _to_int(capacity.get("available_slots"))
            if claim_enabled:
                row["available_slots_total"] += available_slots
                row["claimable_available_slots_total"] = (
                    _to_int(row.get("claimable_available_slots_total"))
                    + available_slots
                )
            runner_id = str(heartbeat.get("runner_id") or "").strip()
            if runner_id:
                row["runner_ids"].append(runner_id)

    for row in capacity_by_queue.values():
        max_inflight = _to_int(row.get("max_inflight_total"))
        if max_inflight > 0:
            row["utilization_ratio"] = _to_int(row.get("inflight_total")) / max_inflight
    return capacity_by_queue


async def build_live_queue_utilization(
    *,
    queue_stores: list[Any] | None = None,
    scan_limit: int | None = None,
    now_epoch: float | None = None,
    default_queue_stores_func: Callable[[], list[Any]],
    read_route_identity_projections_func: Callable[
        [Any, list[str]], Awaitable[dict[str, dict[str, Any]]]
    ],
    list_active_runner_resource_heartbeats_func: Callable[
        [Any], Awaitable[list[dict[str, Any]]]
    ],
) -> dict[str, Any]:
    stores = queue_stores if queue_stores is not None else default_queue_stores_func()
    clamped_limit = _clamped_scan_limit(scan_limit)
    captured_epoch = float(now_epoch if now_epoch is not None else time.time())
    queue_depths_by_name: dict[str, dict[str, int]] = {}
    visible_lanes_by_queue: dict[str, list[dict[str, Any]]] = {}
    visible_lane_count: dict[str, int] = {}
    errors: list[dict[str, Any]] = []

    for queue_store in stores:
        queue_name = str(getattr(queue_store, "pack_id", "") or "").strip()
        if not queue_name:
            continue
        try:
            queue_depths_by_name[queue_name] = await queue_depths(queue_store)
            task_ids = await pending_task_ids(queue_store, scan_limit=clamped_limit)
            client = await queue_store._get_client()
            projections = await read_route_identity_projections_func(client, task_ids)
            lanes = visible_lanes(task_ids=task_ids, projections=projections)
            visible_lanes_by_queue[queue_name] = lanes
            visible_lane_count[queue_name] = len(lanes)
        except Exception as exc:
            errors.append({"queue_shard": queue_name, "error": str(exc)})
            queue_depths_by_name.setdefault(
                queue_name,
                {
                    "pending": 0,
                    "processing": 0,
                    "delayed": 0,
                    "deadletter": 0,
                },
            )
            visible_lanes_by_queue.setdefault(queue_name, [])
            visible_lane_count.setdefault(queue_name, 0)

    queue_names = list(queue_depths_by_name.keys())
    heartbeats = await active_heartbeats(
        stores,
        list_active_runner_resource_heartbeats_func=(
            list_active_runner_resource_heartbeats_func
        ),
    )
    capacity_by_queue = capacity_by_queue_shard(
        queue_names=queue_names,
        heartbeats=heartbeats,
    )
    utilization_ratio_by_queue = {
        queue_name: capacity.get("utilization_ratio")
        for queue_name, capacity in capacity_by_queue.items()
    }

    return {
        "source": "live_redis_bounded",
        "captured_at": _iso_from_epoch(captured_epoch),
        "captured_at_epoch": captured_epoch,
        "scan_limit": clamped_limit,
        "queue_depths": queue_depths_by_name,
        "capacity_by_queue_shard": capacity_by_queue,
        "visible_lanes": visible_lanes_by_queue,
        "visible_lane_count": visible_lane_count,
        "utilization_ratio_by_queue_shard": utilization_ratio_by_queue,
        "degraded": bool(errors),
        "errors": errors,
    }
