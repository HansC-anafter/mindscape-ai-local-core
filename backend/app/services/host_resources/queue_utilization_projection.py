"""Projection helpers for Resource Console queue utilization responses."""

from __future__ import annotations

from typing import Any


_QUEUE_SCOPED_MAP_KEYS = (
    "captured_at_by_queue_shard",
    "queue_depths",
    "capacity_by_queue_shard",
    "visible_lanes",
    "visible_lane_count",
    "resource_lanes",
    "resource_lane_count",
    "active_route_lanes",
    "active_route_lane_count",
    "backlog_summary_by_queue_shard",
    "backlog_by_queue_shard",
    "freshness_by_queue_shard",
    "snapshot_fallback_by_queue_shard",
    "utilization_ratio_by_queue_shard",
)


def _queue_names(snapshot: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for key in _QUEUE_SCOPED_MAP_KEYS:
        value = snapshot.get(key)
        if isinstance(value, dict):
            names.update(str(item) for item in value.keys() if str(item).strip())
    return names


def _scoped_map(value: Any, queue_shard: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    if queue_shard not in value:
        return {}
    return {queue_shard: value.get(queue_shard)}


def _compact_backlog_summary(summary: dict[str, Any]) -> dict[str, Any]:
    by_reason = summary.get("by_blocked_reason")
    reason_rows = []
    if isinstance(by_reason, dict):
        reason_rows = sorted(
            (
                (str(reason), int(count or 0))
                for reason, count in by_reason.items()
                if int(count or 0) > 0
            ),
            key=lambda item: item[1],
            reverse=True,
        )[:4]
    return {
        "pending_total": int(summary.get("pending_total") or 0),
        "running_total": int(summary.get("running_total") or 0),
        "blocked_total": int(summary.get("blocked_total") or 0),
        "ready_pending_total": int(summary.get("ready_pending_total") or 0),
        "cold_pending_total": int(summary.get("cold_pending_total") or 0),
        "unclassified_pending_total": int(
            summary.get("unclassified_pending_total") or 0
        ),
        "by_blocked_reason": dict(reason_rows),
        "by_pack": {},
    }


def project_queue_utilization_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return the compact Resource Console list projection."""

    projected = dict(snapshot)
    projected["view"] = "summary"
    projected["visible_lanes"] = {}
    projected["resource_lanes"] = {}
    projected["active_route_lanes"] = {}
    projected["backlog_by_queue_shard"] = {}
    projected["snapshot_fallback_by_queue_shard"] = {}

    summaries: dict[str, Any] = {}
    raw_summaries = snapshot.get("backlog_summary_by_queue_shard")
    if isinstance(raw_summaries, dict):
        for queue_shard, summary in raw_summaries.items():
            if isinstance(summary, dict):
                summaries[str(queue_shard)] = _compact_backlog_summary(summary)
    projected["backlog_summary_by_queue_shard"] = summaries
    return projected


def project_queue_utilization_detail(
    snapshot: dict[str, Any],
    *,
    queue_shard: str,
) -> dict[str, Any]:
    """Return detail data scoped to one queue shard."""

    normalized = str(queue_shard or "").strip()
    if not normalized:
        raise ValueError("queue_shard_required")
    if normalized not in _queue_names(snapshot):
        raise ValueError("queue_shard_not_found")

    projected = dict(snapshot)
    projected["view"] = "detail"
    projected["queue_shard"] = normalized
    for key in _QUEUE_SCOPED_MAP_KEYS:
        projected[key] = _scoped_map(snapshot.get(key), normalized)
    return projected
