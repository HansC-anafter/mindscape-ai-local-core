"""Low-cardinality runner queue utilization snapshots."""

from __future__ import annotations

import asyncio
from typing import Any

from backend.app.services.runner_resources import list_active_runner_resource_heartbeats
from backend.app.services.runner_topology import RUNNER_READY_QUEUE_ORDER
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore

from .dynamic_lane_store import list_dynamic_lanes, list_dynamic_queue_shards
from .queue_backlog_aggregates import get_queue_backlog_aggregates
from .queue_utilization_live import (
    active_heartbeats as _live_active_heartbeats,
    build_live_queue_utilization as _build_live_queue_utilization,
    capacity_by_queue_shard as _capacity_by_queue_shard,
    default_queue_stores as _live_default_queue_stores,
    pending_task_ids as _pending_task_ids,
    queue_depths as _queue_depths,
    resource_lanes_by_queue as _resource_lanes_by_queue,
    visible_lane_identity as _visible_lane_identity,
    visible_lanes as _visible_lanes,
)
from .queue_utilization_snapshot_store import (
    QueueUtilizationSnapshotStore,
    get_latest_queue_utilization_snapshot as _get_latest_queue_utilization_snapshot,
    row_mapping as _row_mapping,
    snapshot_rows_to_response as _snapshot_rows_to_response,
)
from .queue_utilization_support import (
    MAX_VISIBLE_SCAN_LIMIT,
    SNAPSHOT_RETENTION_DAYS,
    SNAPSHOT_WRITER_LEASE_KEY,
    SNAPSHOT_WRITER_LEASE_SECONDS,
    _clamped_scan_limit,
    _datetime_from_epoch,
    _iso_from_epoch,
    _normalize_task_id,
    _to_int,
    _utc_now,
)
from .queue_utilization_writer import (
    acquire_snapshot_writer_lease as _writer_acquire_snapshot_writer_lease,
    write_queue_utilization_snapshot_if_leader as _write_queue_utilization_snapshot_if_leader,
)
from .route_identity_projection import read_route_identity_projections


def _default_queue_stores() -> list[RedisRunnerQueueStore]:
    return _live_default_queue_stores(
        ready_queue_order=RUNNER_READY_QUEUE_ORDER,
        list_dynamic_queue_shards_func=list_dynamic_queue_shards,
        queue_store_cls=RedisRunnerQueueStore,
    )


def _empty_current_capacity() -> dict[str, Any]:
    return {
        "active_runner_count": 0,
        "claimable_runner_count": 0,
        "claim_blocked_runner_count": 0,
        "claim_blocked_reasons": [],
        "resource_admission": [],
        "max_inflight_total": 0,
        "inflight_total": 0,
        "available_slots_total": 0,
        "claimable_available_slots_total": 0,
        "utilization_ratio": None,
        "runner_ids": [],
    }


async def _active_heartbeats(queue_stores: list[Any]) -> list[dict[str, Any]]:
    return await _live_active_heartbeats(
        queue_stores,
        list_active_runner_resource_heartbeats_func=(
            list_active_runner_resource_heartbeats
        ),
    )


async def build_live_queue_utilization(
    *,
    queue_stores: list[Any] | None = None,
    scan_limit: int | None = None,
    now_epoch: float | None = None,
) -> dict[str, Any]:
    return await _build_live_queue_utilization(
        queue_stores=queue_stores,
        scan_limit=scan_limit,
        now_epoch=now_epoch,
        default_queue_stores_func=_default_queue_stores,
        read_route_identity_projections_func=read_route_identity_projections,
        list_dynamic_lanes_func=list_dynamic_lanes,
        list_active_runner_resource_heartbeats_func=(
            list_active_runner_resource_heartbeats
        ),
    )


def get_latest_queue_utilization_snapshot(
    *,
    store: QueueUtilizationSnapshotStore | None = None,
) -> dict[str, Any]:
    return _get_latest_queue_utilization_snapshot(
        store=store,
        store_cls=QueueUtilizationSnapshotStore,
    )


async def get_latest_queue_utilization_snapshot_with_resource_lanes(
    *,
    store: QueueUtilizationSnapshotStore | None = None,
    backlog_queue_shards: list[str] | None = None,
    include_backlog_breakdowns: bool = True,
    include_active_route_lanes: bool = True,
) -> dict[str, Any]:
    snapshot = await asyncio.to_thread(get_latest_queue_utilization_snapshot, store=store)
    errors = list(snapshot.get("errors") or [])
    try:
        live = await build_live_queue_utilization()
    except Exception as exc:
        errors.append({"queue_shard": "*", "error": str(exc)})
        live = {
            "source": "live_redis_unavailable",
            "captured_at": _utc_now().isoformat(),
            "captured_at_by_queue_shard": {},
            "queue_depths": {},
            "capacity_by_queue_shard": {},
            "visible_lanes": {},
            "visible_lane_count": {},
            "resource_lanes": {},
            "resource_lane_count": {},
            "utilization_ratio_by_queue_shard": {},
            "degraded": True,
            "errors": [],
        }

    live_queue_depths = dict(live.get("queue_depths") or {})
    live_capacity_by_queue = dict(live.get("capacity_by_queue_shard") or {})
    live_visible_lanes = dict(live.get("visible_lanes") or {})
    live_visible_lane_count = dict(live.get("visible_lane_count") or {})
    live_resource_lanes = dict(live.get("resource_lanes") or {})
    live_resource_lane_count = dict(live.get("resource_lane_count") or {})
    live_utilization_by_queue = dict(live.get("utilization_ratio_by_queue_shard") or {})
    live_captured_at_by_queue = dict(live.get("captured_at_by_queue_shard") or {})

    snapshot_queue_depths = dict(snapshot.get("queue_depths") or {})
    snapshot_capacity_by_queue = dict(snapshot.get("capacity_by_queue_shard") or {})
    snapshot_visible_lanes = dict(snapshot.get("visible_lanes") or {})
    snapshot_visible_lane_count = dict(snapshot.get("visible_lane_count") or {})
    snapshot_captured_at_by_queue = dict(snapshot.get("captured_at_by_queue_shard") or {})

    queue_names = set(live_queue_depths.keys())
    queue_names.update(live_capacity_by_queue.keys())
    queue_names.update(live_visible_lanes.keys())
    queue_names.update(live_visible_lane_count.keys())
    queue_names.update(live_resource_lanes.keys())
    queue_names.update(live_resource_lane_count.keys())
    queue_names.update(snapshot_queue_depths.keys())
    queue_names.update(snapshot_capacity_by_queue.keys())
    queue_names.update(snapshot_visible_lanes.keys())

    backlog_query_shards = [
        str(name).strip()
        for name in (backlog_queue_shards or sorted(queue_names))
        if str(name or "").strip()
    ]
    backlog = await asyncio.to_thread(
        get_queue_backlog_aggregates,
        queue_shards=backlog_query_shards or None,
        include_breakdowns=include_backlog_breakdowns,
        include_active_routes=include_active_route_lanes,
    )
    errors.extend(backlog.get("errors") or [])
    queue_names.update(backlog.get("known_queue_shards") or [])
    queue_names.update((backlog.get("backlog_summary_by_queue_shard") or {}).keys())
    queue_names.update((backlog.get("active_route_lanes") or {}).keys())

    sorted_queue_names = sorted(str(name) for name in queue_names if str(name).strip())
    queue_depths: dict[str, dict[str, int]] = {}
    capacity_by_queue: dict[str, dict[str, Any]] = {}
    visible_lanes: dict[str, list[dict[str, Any]]] = {}
    visible_lane_count: dict[str, int] = {}
    resource_lanes: dict[str, list[dict[str, Any]]] = {}
    resource_lane_count: dict[str, int] = {}
    utilization_by_queue: dict[str, float | None] = {}
    captured_at_by_queue: dict[str, str] = {}
    snapshot_fallbacks: dict[str, dict[str, Any]] = {}
    freshness_by_queue: dict[str, dict[str, Any]] = {}

    for queue_name in sorted_queue_names:
        live_depth = live_queue_depths.get(queue_name)
        snapshot_depth = snapshot_queue_depths.get(queue_name)
        if isinstance(live_depth, dict):
            queue_depths[queue_name] = {
                "pending": _to_int(live_depth.get("pending")),
                "processing": _to_int(live_depth.get("processing")),
                "delayed": _to_int(live_depth.get("delayed")),
                "deadletter": _to_int(live_depth.get("deadletter")),
            }
            queue_depths_source = "live_redis"
        elif isinstance(snapshot_depth, dict):
            queue_depths[queue_name] = {
                "pending": _to_int(snapshot_depth.get("pending")),
                "processing": _to_int(snapshot_depth.get("processing")),
                "delayed": _to_int(snapshot_depth.get("delayed")),
                "deadletter": _to_int(snapshot_depth.get("deadletter")),
            }
            queue_depths_source = "postgres_snapshot"
        else:
            queue_depths[queue_name] = {
                "pending": 0,
                "processing": 0,
                "delayed": 0,
                "deadletter": 0,
            }
            queue_depths_source = "none"

        live_capacity = live_capacity_by_queue.get(queue_name)
        snapshot_capacity = snapshot_capacity_by_queue.get(queue_name)
        if isinstance(live_capacity, dict):
            capacity_by_queue[queue_name] = dict(live_capacity)
            capacity_source = "live_heartbeat"
        elif isinstance(snapshot_capacity, dict):
            capacity_by_queue[queue_name] = _empty_current_capacity()
            capacity_source = "postgres_snapshot"
        else:
            capacity_by_queue[queue_name] = _empty_current_capacity()
            capacity_source = "none"

        live_lanes = live_visible_lanes.get(queue_name)
        snapshot_lanes = snapshot_visible_lanes.get(queue_name)
        if isinstance(live_lanes, list):
            visible_lanes[queue_name] = live_lanes
            visible_lanes_source = "live_redis_route_projection"
        elif isinstance(snapshot_lanes, list):
            visible_lanes[queue_name] = snapshot_lanes
            visible_lanes_source = "postgres_snapshot"
        else:
            visible_lanes[queue_name] = []
            visible_lanes_source = "none"
        visible_lane_count[queue_name] = _to_int(
            live_visible_lane_count.get(queue_name)
            if queue_name in live_visible_lane_count
            else snapshot_visible_lane_count.get(queue_name),
            len(visible_lanes[queue_name]),
        )

        resource_queue_lanes = live_resource_lanes.get(queue_name)
        if isinstance(resource_queue_lanes, list):
            resource_lanes[queue_name] = resource_queue_lanes
        else:
            resource_lanes[queue_name] = []
        resource_lane_count[queue_name] = _to_int(
            live_resource_lane_count.get(queue_name),
            len(resource_lanes[queue_name]),
        )

        utilization = capacity_by_queue[queue_name].get("utilization_ratio")
        if queue_name in live_utilization_by_queue:
            utilization = live_utilization_by_queue.get(queue_name)
        utilization_by_queue[queue_name] = utilization

        captured_at = live_captured_at_by_queue.get(queue_name)
        if not captured_at:
            captured_at = snapshot_captured_at_by_queue.get(queue_name)
        if not captured_at:
            captured_at = live.get("captured_at") or snapshot.get("captured_at")
        if captured_at:
            captured_at_by_queue[queue_name] = str(captured_at)

        snapshot_fallbacks[queue_name] = {
            "captured_at": snapshot_captured_at_by_queue.get(queue_name),
            "queue_depths": snapshot_depth if isinstance(snapshot_depth, dict) else None,
            "capacity": snapshot_capacity if isinstance(snapshot_capacity, dict) else None,
            "visible_lanes": snapshot_lanes if isinstance(snapshot_lanes, list) else None,
            "visible_lane_count": snapshot_visible_lane_count.get(queue_name),
        }
        freshness_by_queue[queue_name] = {
            "queue_depths_source": queue_depths_source,
            "capacity_source": capacity_source,
            "visible_lanes_source": visible_lanes_source,
            "resource_lanes_source": "live_heartbeat_or_registry"
            if resource_lanes[queue_name]
            else "none",
            "backlog_source": "postgres_tasks"
            if queue_name in (backlog.get("backlog_summary_by_queue_shard") or {})
            else "none",
            "live_captured_at": live_captured_at_by_queue.get(queue_name)
            or live.get("captured_at"),
            "snapshot_captured_at": snapshot_captured_at_by_queue.get(queue_name),
            "stale": queue_depths_source == "postgres_snapshot"
            or capacity_source == "postgres_snapshot"
            or visible_lanes_source == "postgres_snapshot",
        }

    return {
        "source": "live_resource_console",
        "captured_at": live.get("captured_at") or snapshot.get("captured_at"),
        "captured_at_by_queue_shard": captured_at_by_queue,
        "queue_depths": queue_depths,
        "capacity_by_queue_shard": capacity_by_queue,
        "visible_lanes": visible_lanes,
        "visible_lane_count": visible_lane_count,
        "resource_lanes": resource_lanes,
        "resource_lane_count": resource_lane_count,
        "active_route_lanes": backlog.get("active_route_lanes") or {},
        "active_route_lane_count": backlog.get("active_route_lane_count") or {},
        "backlog_summary_by_queue_shard": (
            backlog.get("backlog_summary_by_queue_shard") or {}
        ),
        "backlog_by_queue_shard": backlog.get("backlog_by_queue_shard") or {},
        "freshness_by_queue_shard": freshness_by_queue,
        "snapshot_fallback_by_queue_shard": snapshot_fallbacks,
        "utilization_ratio_by_queue_shard": utilization_by_queue,
        "scan_limit": live.get("scan_limit"),
        "degraded": bool(live.get("degraded")) or bool(snapshot.get("degraded")) or bool(errors),
        "errors": [*list(live.get("errors") or []), *errors],
    }


async def _acquire_snapshot_writer_lease(queue_store: Any) -> bool:
    return await _writer_acquire_snapshot_writer_lease(queue_store)


async def write_queue_utilization_snapshot_if_leader(
    *,
    queue_stores: list[Any] | None = None,
    scan_limit: int | None = None,
    store: QueueUtilizationSnapshotStore | None = None,
) -> dict[str, Any]:
    return await _write_queue_utilization_snapshot_if_leader(
        queue_stores=queue_stores,
        scan_limit=scan_limit,
        store=store,
        default_queue_stores_func=_default_queue_stores,
        acquire_snapshot_writer_lease_func=_acquire_snapshot_writer_lease,
        build_live_queue_utilization_func=build_live_queue_utilization,
        snapshot_store_cls=QueueUtilizationSnapshotStore,
    )
