"""Postgres snapshot store for queue utilization."""

from __future__ import annotations

import json
import time
from typing import Any, Callable

from sqlalchemy import text

from backend.app.services.stores.postgres_base import PostgresStoreBase

from .queue_utilization_support import (
    SNAPSHOT_RETENTION_DAYS,
    _datetime_from_epoch,
    _to_int,
    _utc_now,
)


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
        return snapshot_rows_to_response(rows)


def row_mapping(row: Any) -> dict[str, Any]:
    if hasattr(row, "_mapping"):
        return dict(row._mapping)
    return dict(row or {})


def snapshot_rows_to_response(rows: list[Any]) -> dict[str, Any]:
    queue_depths: dict[str, dict[str, int]] = {}
    capacity_by_queue: dict[str, dict[str, Any]] = {}
    visible_lanes: dict[str, list[dict[str, Any]]] = {}
    visible_lane_count: dict[str, int] = {}
    captured_at_values: list[str] = []

    for row in rows:
        data = row_mapping(row)
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
    store_cls: Callable[[], QueueUtilizationSnapshotStore],
) -> dict[str, Any]:
    snapshot_store = store or store_cls()
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
