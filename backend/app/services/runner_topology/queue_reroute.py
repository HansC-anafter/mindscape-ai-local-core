"""Bounded pending queue reroute helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.services.host_resources.dynamic_lane_store import list_dynamic_queue_shards
from backend.app.services.runner_topology.partitions import RUNNER_READY_QUEUE_ORDER
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore


@dataclass(frozen=True)
class PendingTaskRerouteResult:
    task_id: str
    target_shard: str
    removed_count: int
    pushed: bool
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "target_shard": self.target_shard,
            "removed_count": self.removed_count,
            "pushed": self.pushed,
            "reason": self.reason,
        }


def registered_pending_queue_shards() -> list[str]:
    shards: list[str] = []
    for shard in [*RUNNER_READY_QUEUE_ORDER, *list_dynamic_queue_shards()]:
        normalized = str(shard or "").strip()
        if normalized and normalized not in shards:
            shards.append(normalized)
    return shards


async def reroute_pending_task(
    task_id: str,
    *,
    target_shard: str,
    route_identity: dict[str, Any] | None = None,
    source_shards: list[str] | tuple[str, ...] | None = None,
) -> PendingTaskRerouteResult:
    normalized_task_id = str(task_id or "").strip()
    normalized_target = str(target_shard or "").strip()
    if not normalized_task_id:
        return PendingTaskRerouteResult("", normalized_target, 0, False, "task_id_required")
    if not normalized_target:
        return PendingTaskRerouteResult(normalized_task_id, "", 0, False, "target_shard_required")
    resolved_sources = [
        str(shard or "").strip()
        for shard in (source_shards or registered_pending_queue_shards())
        if str(shard or "").strip()
    ]
    target_queue = RedisRunnerQueueStore(pack_id=normalized_target)
    reroute = await target_queue.reroute_pending_task(
        normalized_task_id,
        source_shards=resolved_sources,
        route_identity=route_identity,
    )
    removed_count = int(reroute.get("removed_count") or 0)
    pushed = bool(reroute.get("pushed"))
    reason = None if pushed else "skipped_not_in_pending_queue"
    return PendingTaskRerouteResult(
        normalized_task_id,
        normalized_target,
        removed_count,
        pushed,
        reason,
    )
