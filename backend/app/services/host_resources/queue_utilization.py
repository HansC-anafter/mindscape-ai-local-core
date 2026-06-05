"""Low-cardinality runner queue utilization snapshots."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from backend.app.services.runner_resources import list_active_runner_resource_heartbeats
from backend.app.services.runner_topology import RUNNER_READY_QUEUE_ORDER
from backend.app.services.stores.postgres_base import PostgresStoreBase
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore

from .dynamic_lane_store import list_dynamic_queue_shards
from .route_identity_projection import read_route_identity_projections


SNAPSHOT_WRITER_LEASE_KEY = "mindscape:runner_queue_utilization:snapshot_writer"
SNAPSHOT_WRITER_LEASE_SECONDS = 55
SNAPSHOT_RETENTION_DAYS = 14
MAX_VISIBLE_SCAN_LIMIT = 128


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_from_epoch(epoch: float) -> str:
    return datetime.fromtimestamp(float(epoch), timezone.utc).isoformat()


def _datetime_from_epoch(epoch: float) -> datetime:
    return datetime.fromtimestamp(float(epoch), timezone.utc)


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _normalize_task_id(raw_value: object) -> str:
    if isinstance(raw_value, bytes):
        return raw_value.decode()
    return str(raw_value)


def _clamped_scan_limit(value: int | None = None) -> int:
    if value is None:
        value = _to_int(
            os.getenv("LOCAL_CORE_RUNNER_PLAYBOOK_FAIR_SCAN_LIMIT"),
            MAX_VISIBLE_SCAN_LIMIT,
        )
    return max(
        1,
        min(_to_int(value, MAX_VISIBLE_SCAN_LIMIT), MAX_VISIBLE_SCAN_LIMIT),
    )


def _default_queue_stores() -> list[RedisRunnerQueueStore]:
    queue_shards: list[str] = []
    for queue_shard in [*RUNNER_READY_QUEUE_ORDER, *list_dynamic_queue_shards()]:
        normalized = str(queue_shard or "").strip()
        if normalized and normalized not in queue_shards:
            queue_shards.append(normalized)
    return [
        RedisRunnerQueueStore(pack_id=queue_shard)
        for queue_shard in queue_shards
    ]


async def _pending_task_ids(queue_store: Any, *, scan_limit: int) -> list[str]:
    client = await queue_store._get_client()
    if not client:
        return []
    raw_ids = await client.lrange(queue_store.q_pending, 0, max(0, scan_limit - 1))
    return [
        _normalize_task_id(raw).strip()
        for raw in raw_ids
        if _normalize_task_id(raw).strip()
    ]


async def _queue_depths(queue_store: Any) -> dict[str, int]:
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


def _visible_lane_identity(projection: dict[str, Any]) -> tuple[str, str]:
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


def _visible_lanes(
    *,
    task_ids: list[str],
    projections: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    lanes: dict[str, dict[str, Any]] = {}
    for queue_position, task_id in enumerate(task_ids):
        projection = projections.get(task_id)
        if not projection:
            continue
        lane_type, lane_value = _visible_lane_identity(projection)
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


async def _active_heartbeats(queue_stores: list[Any]) -> list[dict[str, Any]]:
    for queue_store in queue_stores:
        try:
            heartbeats = await list_active_runner_resource_heartbeats(queue_store)
        except Exception:
            heartbeats = []
        if heartbeats:
            return heartbeats
    return []


def _capacity_by_queue_shard(
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
) -> dict[str, Any]:
    stores = queue_stores if queue_stores is not None else _default_queue_stores()
    clamped_limit = _clamped_scan_limit(scan_limit)
    captured_epoch = float(now_epoch if now_epoch is not None else time.time())
    queue_depths: dict[str, dict[str, int]] = {}
    visible_lanes_by_queue: dict[str, list[dict[str, Any]]] = {}
    visible_lane_count: dict[str, int] = {}
    errors: list[dict[str, Any]] = []

    for queue_store in stores:
        queue_name = str(getattr(queue_store, "pack_id", "") or "").strip()
        if not queue_name:
            continue
        try:
            queue_depths[queue_name] = await _queue_depths(queue_store)
            task_ids = await _pending_task_ids(queue_store, scan_limit=clamped_limit)
            client = await queue_store._get_client()
            projections = await read_route_identity_projections(client, task_ids)
            visible_lanes = _visible_lanes(task_ids=task_ids, projections=projections)
            visible_lanes_by_queue[queue_name] = visible_lanes
            visible_lane_count[queue_name] = len(visible_lanes)
        except Exception as exc:
            errors.append({"queue_shard": queue_name, "error": str(exc)})
            queue_depths.setdefault(
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

    queue_names = list(queue_depths.keys())
    heartbeats = await _active_heartbeats(stores)
    capacity_by_queue = _capacity_by_queue_shard(
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
        "queue_depths": queue_depths,
        "capacity_by_queue_shard": capacity_by_queue,
        "visible_lanes": visible_lanes_by_queue,
        "visible_lane_count": visible_lane_count,
        "utilization_ratio_by_queue_shard": utilization_ratio_by_queue,
        "degraded": bool(errors),
        "errors": errors,
    }


class QueueUtilizationSnapshotStore(PostgresStoreBase):
    """Append-only queue utilization snapshot store."""

    def save_snapshot_batch(self, snapshot: dict[str, Any]) -> int:
        captured_at = _datetime_from_epoch(
            float(snapshot.get("captured_at_epoch") or time.time())
        )
        queue_depths = snapshot.get("queue_depths")
        capacities = snapshot.get("capacity_by_queue_shard")
        visible_lanes = snapshot.get("visible_lanes")
        if not isinstance(queue_depths, dict):
            return 0
        if not isinstance(capacities, dict):
            capacities = {}
        if not isinstance(visible_lanes, dict):
            visible_lanes = {}

        inserted = 0
        with self.transaction() as conn:
            for queue_shard, depths in queue_depths.items():
                if not isinstance(depths, dict):
                    continue
                capacity = capacities.get(queue_shard)
                if not isinstance(capacity, dict):
                    capacity = {}
                lanes = visible_lanes.get(queue_shard)
                if not isinstance(lanes, list):
                    lanes = []
                conn.execute(
                    text(
                        """
                        INSERT INTO runner_queue_capacity_snapshots (
                            captured_at,
                            queue_shard,
                            pending_depth,
                            processing_depth,
                            delayed_depth,
                            deadletter_depth,
                            visible_lane_count,
                            visible_lanes_json,
                            active_runner_count,
                            max_inflight_total,
                            inflight_total,
                            available_slots_total
                        ) VALUES (
                            :captured_at,
                            :queue_shard,
                            :pending_depth,
                            :processing_depth,
                            :delayed_depth,
                            :deadletter_depth,
                            :visible_lane_count,
                            CAST(:visible_lanes_json AS JSONB),
                            :active_runner_count,
                            :max_inflight_total,
                            :inflight_total,
                            :available_slots_total
                        )
                        """
                    ),
                    {
                        "captured_at": captured_at,
                        "queue_shard": str(queue_shard),
                        "pending_depth": _to_int(depths.get("pending")),
                        "processing_depth": _to_int(depths.get("processing")),
                        "delayed_depth": _to_int(depths.get("delayed")),
                        "deadletter_depth": _to_int(depths.get("deadletter")),
                        "visible_lane_count": len(lanes),
                        "visible_lanes_json": self.serialize_json(lanes),
                        "active_runner_count": _to_int(
                            capacity.get("active_runner_count")
                        ),
                        "max_inflight_total": _to_int(
                            capacity.get("max_inflight_total")
                        ),
                        "inflight_total": _to_int(capacity.get("inflight_total")),
                        "available_slots_total": _to_int(
                            capacity.get("available_slots_total")
                        ),
                    },
                )
                inserted += 1
        return inserted

    def delete_old_snapshots(
        self,
        *,
        retention_days: int = SNAPSHOT_RETENTION_DAYS,
    ) -> int:
        with self.transaction() as conn:
            result = conn.execute(
                text(
                    """
                    DELETE FROM runner_queue_capacity_snapshots
                    WHERE captured_at < NOW() - (:retention_days * INTERVAL '1 day')
                    """
                ),
                {
                    "retention_days": max(
                        1,
                        int(retention_days or SNAPSHOT_RETENTION_DAYS),
                    )
                },
            )
        return int(result.rowcount or 0)

    def latest_snapshot(self) -> dict[str, Any] | None:
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT DISTINCT ON (queue_shard)
                        captured_at,
                        queue_shard,
                        pending_depth,
                        processing_depth,
                        delayed_depth,
                        deadletter_depth,
                        visible_lane_count,
                        visible_lanes_json,
                        active_runner_count,
                        max_inflight_total,
                        inflight_total,
                        available_slots_total
                    FROM runner_queue_capacity_snapshots
                    ORDER BY queue_shard, captured_at DESC
                    """
                )
            ).fetchall()
        if not rows:
            return None
        return _snapshot_rows_to_response(rows)


def _row_mapping(row: Any) -> dict[str, Any]:
    if hasattr(row, "_mapping"):
        return dict(row._mapping)
    return dict(row or {})


def _snapshot_rows_to_response(rows: list[Any]) -> dict[str, Any]:
    queue_depths: dict[str, dict[str, int]] = {}
    capacity_by_queue: dict[str, dict[str, Any]] = {}
    visible_lanes: dict[str, list[dict[str, Any]]] = {}
    visible_lane_count: dict[str, int] = {}
    captured_at_values: list[str] = []

    for row in rows:
        data = _row_mapping(row)
        queue_shard = str(data.get("queue_shard") or "").strip()
        if not queue_shard:
            continue
        captured_at = data.get("captured_at")
        if hasattr(captured_at, "isoformat"):
            captured_at_values.append(captured_at.isoformat())
        queue_depths[queue_shard] = {
            "pending": _to_int(data.get("pending_depth")),
            "processing": _to_int(data.get("processing_depth")),
            "delayed": _to_int(data.get("delayed_depth")),
            "deadletter": _to_int(data.get("deadletter_depth")),
        }
        max_inflight = _to_int(data.get("max_inflight_total"))
        inflight = _to_int(data.get("inflight_total"))
        utilization_ratio = inflight / max_inflight if max_inflight > 0 else None
        capacity_by_queue[queue_shard] = {
            "active_runner_count": _to_int(data.get("active_runner_count")),
            "max_inflight_total": max_inflight,
            "inflight_total": inflight,
            "available_slots_total": _to_int(data.get("available_slots_total")),
            "utilization_ratio": utilization_ratio,
            "runner_ids": [],
        }
        lanes = data.get("visible_lanes_json")
        if isinstance(lanes, str):
            try:
                lanes = json.loads(lanes)
            except Exception:
                lanes = []
        if not isinstance(lanes, list):
            lanes = []
        visible_lanes[queue_shard] = lanes
        visible_lane_count[queue_shard] = _to_int(
            data.get("visible_lane_count"),
            len(lanes),
        )

    return {
        "source": "postgres_snapshot",
        "captured_at": (
            max(captured_at_values)
            if captured_at_values
            else _utc_now().isoformat()
        ),
        "queue_depths": queue_depths,
        "capacity_by_queue_shard": capacity_by_queue,
        "visible_lanes": visible_lanes,
        "visible_lane_count": visible_lane_count,
        "utilization_ratio_by_queue_shard": {
            queue_shard: capacity.get("utilization_ratio")
            for queue_shard, capacity in capacity_by_queue.items()
        },
        "degraded": False,
        "errors": [],
    }


def get_latest_queue_utilization_snapshot(
    *,
    store: QueueUtilizationSnapshotStore | None = None,
) -> dict[str, Any]:
    snapshot_store = store or QueueUtilizationSnapshotStore()
    try:
        snapshot = snapshot_store.latest_snapshot()
    except Exception as exc:
        return {
            "source": "postgres_snapshot",
            "captured_at": _utc_now().isoformat(),
            "queue_depths": {},
            "capacity_by_queue_shard": {},
            "visible_lanes": {},
            "visible_lane_count": {},
            "utilization_ratio_by_queue_shard": {},
            "degraded": True,
            "errors": [{"error": str(exc)}],
        }
    if snapshot is not None:
        return snapshot
    return {
        "source": "postgres_snapshot",
        "captured_at": _utc_now().isoformat(),
        "queue_depths": {},
        "capacity_by_queue_shard": {},
        "visible_lanes": {},
        "visible_lane_count": {},
        "utilization_ratio_by_queue_shard": {},
        "degraded": True,
        "errors": [{"error": "queue_utilization_snapshot_unavailable"}],
    }


async def _acquire_snapshot_writer_lease(queue_store: Any) -> bool:
    client = await queue_store._get_client()
    if not client:
        return False
    token = f"{os.getpid()}:{time.time()}"
    return bool(
        await client.set(
            SNAPSHOT_WRITER_LEASE_KEY,
            token,
            nx=True,
            ex=SNAPSHOT_WRITER_LEASE_SECONDS,
        )
    )


async def write_queue_utilization_snapshot_if_leader(
    *,
    queue_stores: list[Any] | None = None,
    scan_limit: int | None = None,
    store: QueueUtilizationSnapshotStore | None = None,
) -> dict[str, Any]:
    stores = queue_stores if queue_stores is not None else _default_queue_stores()
    if not stores:
        return {"written": False, "reason": "no_queue_stores", "inserted": 0}
    lease_store = stores[0]
    try:
        lease_acquired = await _acquire_snapshot_writer_lease(lease_store)
    except Exception as exc:
        return {
            "written": False,
            "reason": "lease_unavailable",
            "inserted": 0,
            "error": str(exc),
        }
    if not lease_acquired:
        return {"written": False, "reason": "lease_held", "inserted": 0}

    snapshot = await build_live_queue_utilization(
        queue_stores=stores,
        scan_limit=scan_limit,
    )
    snapshot_store = store or QueueUtilizationSnapshotStore()
    inserted = snapshot_store.save_snapshot_batch(snapshot)
    snapshot_store.delete_old_snapshots()
    return {
        "written": True,
        "reason": "lease_acquired",
        "inserted": inserted,
        "snapshot": snapshot,
    }
