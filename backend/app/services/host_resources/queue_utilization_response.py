"""Response builder for the Resource Console queue utilization endpoint."""

from __future__ import annotations

from typing import Any

from .queue_utilization import (
    build_live_queue_utilization,
    get_latest_queue_utilization_snapshot_with_resource_lanes,
)
from .queue_utilization_projection import (
    project_queue_utilization_detail,
    project_queue_utilization_summary,
)


async def build_queue_utilization_response(
    *,
    live: bool = False,
    view: str | None = None,
    queue_shard: str | None = None,
) -> dict[str, Any]:
    """Build the canonical queue utilization response projection."""

    if live:
        return await build_live_queue_utilization()

    normalized_view = str(view or "full").strip().lower()
    if normalized_view in {"", "full"}:
        return await get_latest_queue_utilization_snapshot_with_resource_lanes()
    if normalized_view == "summary":
        snapshot = await get_latest_queue_utilization_snapshot_with_resource_lanes(
            include_backlog_breakdowns=False,
            include_active_route_lanes=False,
        )
        return project_queue_utilization_summary(snapshot)
    if normalized_view == "detail":
        normalized_queue = str(queue_shard or "").strip()
        if not normalized_queue:
            raise ValueError("queue_shard_required")
        snapshot = await get_latest_queue_utilization_snapshot_with_resource_lanes(
            backlog_queue_shards=[normalized_queue],
        )
        return project_queue_utilization_detail(
            snapshot,
            queue_shard=normalized_queue,
        )
    raise ValueError("unsupported_queue_utilization_view")
