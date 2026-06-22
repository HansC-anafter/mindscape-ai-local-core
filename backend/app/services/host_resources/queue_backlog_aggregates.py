"""Task backlog aggregates for Resource Console queue cards."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from backend.app.services.stores.postgres_base import PostgresStoreBase

from .queue_utilization_support import _to_int


def _row_mapping(row: Any) -> dict[str, Any]:
    if hasattr(row, "_mapping"):
        return dict(row._mapping)
    return dict(row or {})


def _clean_string(value: Any, fallback: str = "") -> str:
    normalized = str(value or "").strip()
    return normalized or fallback


def _empty_summary() -> dict[str, Any]:
    return {
        "pending_total": 0,
        "running_total": 0,
        "blocked_total": 0,
        "ready_pending_total": 0,
        "cold_pending_total": 0,
        "unclassified_pending_total": 0,
        "by_blocked_reason": {},
        "by_pack": {},
    }


def _add_pack_count(summary: dict[str, Any], pack_id: str, status: str, count: int) -> None:
    by_pack = summary.setdefault("by_pack", {})
    pack_summary = by_pack.setdefault(pack_id, {"pending": 0, "running": 0})
    if status == "running":
        pack_summary["running"] = _to_int(pack_summary.get("running")) + count
    elif status == "pending":
        pack_summary["pending"] = _to_int(pack_summary.get("pending")) + count


def _lane_identity(row: dict[str, Any]) -> tuple[str, str]:
    concurrency_key = _clean_string(row.get("concurrency_key"))
    if concurrency_key:
        return "concurrency_key", concurrency_key
    pack_id = _clean_string(row.get("pack_id"), "unknown")
    return "playbook", pack_id


def backlog_rows_to_response(
    rows: list[Any],
    *,
    route_rows: list[Any] | None = None,
    include_breakdowns: bool = True,
) -> dict[str, Any]:
    summaries: dict[str, dict[str, Any]] = {}
    breakdowns: dict[str, list[dict[str, Any]]] = {}
    lanes_by_queue: dict[str, dict[str, dict[str, Any]]] = {}
    known_queue_shards: list[str] = []

    for row in rows:
        data = _row_mapping(row)
        queue_shard = _clean_string(data.get("queue_shard"))
        if not queue_shard:
            continue
        if queue_shard not in known_queue_shards:
            known_queue_shards.append(queue_shard)

        pack_id = _clean_string(data.get("pack_id"), "unknown")
        status = _clean_string(data.get("status"), "unknown")
        frontier_state = _clean_string(data.get("frontier_state"))
        blocked_reason = _clean_string(data.get("blocked_reason"))
        concurrency_key = _clean_string(data.get("concurrency_key"))
        count = max(0, _to_int(data.get("task_count")))

        summary = summaries.setdefault(queue_shard, _empty_summary())
        _add_pack_count(summary, pack_id, status, count)
        if status == "running":
            summary["running_total"] = _to_int(summary.get("running_total")) + count
        elif status == "pending":
            summary["pending_total"] = _to_int(summary.get("pending_total")) + count
            if blocked_reason:
                summary["blocked_total"] = _to_int(summary.get("blocked_total")) + count
                by_reason = summary.setdefault("by_blocked_reason", {})
                by_reason[blocked_reason] = _to_int(by_reason.get(blocked_reason)) + count
            elif frontier_state == "ready":
                summary["ready_pending_total"] = (
                    _to_int(summary.get("ready_pending_total")) + count
                )
            elif frontier_state == "cold":
                summary["cold_pending_total"] = (
                    _to_int(summary.get("cold_pending_total")) + count
                )
            else:
                summary["unclassified_pending_total"] = (
                    _to_int(summary.get("unclassified_pending_total")) + count
                )

        if include_breakdowns:
            breakdowns.setdefault(queue_shard, []).append(
                {
                    "queue_shard": queue_shard,
                    "pack_id": pack_id,
                    "status": status,
                    "frontier_state": frontier_state,
                    "blocked_reason": blocked_reason,
                    "concurrency_key": concurrency_key,
                    "count": count,
                }
            )

    lane_source_rows = route_rows if route_rows is not None else rows
    for row in lane_source_rows:
        data = _row_mapping(row)
        queue_shard = _clean_string(data.get("queue_shard"))
        if not queue_shard:
            continue
        pack_id = _clean_string(data.get("pack_id"), "unknown")
        status = _clean_string(data.get("status"), "unknown")
        concurrency_key = _clean_string(data.get("concurrency_key"))
        count = max(0, _to_int(data.get("task_count")))
        if status in {"pending", "running"} and count > 0:
            lane_type, lane_value = _lane_identity(data)
            lane_key = f"{lane_type}:{lane_value}"
            queue_lanes = lanes_by_queue.setdefault(queue_shard, {})
            lane = queue_lanes.setdefault(
                lane_key,
                {
                    "lane_key": lane_key,
                    "lane_type": lane_type,
                    "lane_value": lane_value,
                    "count": 0,
                    "first_queue_position": 0,
                    "pack_ids": [],
                    "example_task_ids": [],
                },
            )
            lane["count"] = _to_int(lane.get("count")) + count
            if pack_id and pack_id not in lane["pack_ids"]:
                lane["pack_ids"].append(pack_id)
            if concurrency_key and len(lane["example_task_ids"]) < 3:
                lane["example_task_ids"].append(concurrency_key)

    active_route_lanes = {
        queue_shard: sorted(
            lanes.values(),
            key=lambda lane: (
                str(lane.get("lane_type") or ""),
                str(lane.get("lane_key") or ""),
            ),
        )
        for queue_shard, lanes in lanes_by_queue.items()
    }
    return {
        "backlog_summary_by_queue_shard": summaries,
        "backlog_by_queue_shard": {
            queue_shard: sorted(
                rows,
                key=lambda item: (
                    str(item.get("status") or ""),
                    str(item.get("pack_id") or ""),
                    str(item.get("blocked_reason") or ""),
                    str(item.get("concurrency_key") or ""),
                ),
            )
            for queue_shard, rows in breakdowns.items()
        },
        "active_route_lanes": active_route_lanes,
        "active_route_lane_count": {
            queue_shard: len(lanes) for queue_shard, lanes in active_route_lanes.items()
        },
        "known_queue_shards": sorted(known_queue_shards),
    }


class QueueBacklogAggregateStore(PostgresStoreBase):
    """Read-only grouped task backlog store."""

    def list_rows(self, *, queue_shards: list[str] | None = None) -> list[dict[str, Any]]:
        normalized_shards = [
            str(item).strip()
            for item in (queue_shards or [])
            if str(item or "").strip()
        ]
        clauses = [
            "status IN ('pending', 'running')",
            "task_type IN ('playbook_execution', 'tool_execution')",
            "queue_shard IS NOT NULL",
            "queue_shard <> ''",
        ]
        params: dict[str, Any] = {}
        if normalized_shards:
            clauses.append("queue_shard = ANY(:queue_shards)")
            params["queue_shards"] = normalized_shards
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT
                        queue_shard,
                        pack_id,
                        status,
                        frontier_state,
                        blocked_reason,
                        '' AS concurrency_key,
                        COUNT(*) AS task_count
                    FROM tasks
                    WHERE {" AND ".join(clauses)}
                    GROUP BY
                        queue_shard,
                        status,
                        frontier_state,
                        blocked_reason,
                        pack_id
                    ORDER BY queue_shard, status, task_count DESC
                    """
                ),
                params,
            ).fetchall()
        return [_row_mapping(row) for row in rows]

    def list_active_route_rows(
        self,
        *,
        queue_shards: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        normalized_shards = [
            str(item).strip()
            for item in (queue_shards or [])
            if str(item or "").strip()
        ]
        params: dict[str, Any] = {}
        queue_filter = ""
        if normalized_shards:
            queue_filter = "AND queue_shard = ANY(:queue_shards)"
            params["queue_shards"] = normalized_shards
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT
                        queue_shard,
                        COALESCE(NULLIF(pack_id, ''), 'unknown') AS pack_id,
                        status,
                        COALESCE(frontier_state, '') AS frontier_state,
                        COALESCE(blocked_reason, '') AS blocked_reason,
                        COALESCE(concurrency_key, '') AS concurrency_key,
                        COUNT(*) AS task_count
                    FROM (
                        SELECT
                            queue_shard,
                            pack_id,
                            status,
                            frontier_state,
                            blocked_reason,
                            concurrency_key
                        FROM tasks
                        WHERE status = 'running'
                          AND task_type IN ('playbook_execution', 'tool_execution')
                          AND queue_shard IS NOT NULL
                          AND queue_shard <> ''
                          {queue_filter}
                        UNION ALL
                        SELECT
                            queue_shard,
                            pack_id,
                            status,
                            frontier_state,
                            blocked_reason,
                            concurrency_key
                        FROM tasks
                        WHERE status = 'pending'
                          AND task_type IN ('playbook_execution', 'tool_execution')
                          AND frontier_state = 'ready'
                          AND (blocked_reason IS NULL OR blocked_reason = '')
                          AND queue_shard IS NOT NULL
                          AND queue_shard <> ''
                          {queue_filter}
                    ) AS active_rows
                    GROUP BY
                        queue_shard,
                        COALESCE(NULLIF(pack_id, ''), 'unknown'),
                        status,
                        COALESCE(frontier_state, ''),
                        COALESCE(blocked_reason, ''),
                        COALESCE(concurrency_key, '')
                    ORDER BY queue_shard, status, task_count DESC
                    """
                ),
                params,
            ).fetchall()
        return [_row_mapping(row) for row in rows]


def get_queue_backlog_aggregates(
    *,
    queue_shards: list[str] | None = None,
    store: QueueBacklogAggregateStore | None = None,
    include_breakdowns: bool = True,
    include_active_routes: bool = True,
) -> dict[str, Any]:
    aggregate_store = store or QueueBacklogAggregateStore("core")
    try:
        rows = aggregate_store.list_rows(queue_shards=queue_shards)
        route_rows = (
            aggregate_store.list_active_route_rows(queue_shards=queue_shards)
            if include_active_routes
            else []
        )
        response = backlog_rows_to_response(
            rows,
            route_rows=route_rows,
            include_breakdowns=include_breakdowns,
        )
        response["errors"] = []
        return response
    except Exception as exc:
        return {
            "backlog_summary_by_queue_shard": {},
            "backlog_by_queue_shard": {},
            "active_route_lanes": {},
            "active_route_lane_count": {},
            "known_queue_shards": [],
            "errors": [{"queue_shard": "*", "error": str(exc)}],
        }
