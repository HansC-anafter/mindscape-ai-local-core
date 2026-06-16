"""Low-cardinality runner queue utilization snapshots."""

from __future__ import annotations

from typing import Any

from backend.app.services.runner_resources import list_active_runner_resource_heartbeats
from backend.app.services.runner_topology import RUNNER_READY_QUEUE_ORDER
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore

from .dynamic_lane_store import list_dynamic_queue_shards
from .queue_utilization_live import (
    active_heartbeats as _live_active_heartbeats,
    build_live_queue_utilization as _build_live_queue_utilization,
    capacity_by_queue_shard as _capacity_by_queue_shard,
    default_queue_stores as _live_default_queue_stores,
    pending_task_ids as _pending_task_ids,
    queue_depths as _queue_depths,
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
