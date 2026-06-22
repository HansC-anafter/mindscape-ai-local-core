"""Runner worker Redis ready-queue transport helpers."""

import asyncio
import logging
from typing import Iterable, Optional

from backend.app.models.workspace import TaskStatus
from backend.app.services.runner_topology import (
    DEFAULT_LOCAL_QUEUE_PARTITION,
    RUNNER_READY_QUEUE_ORDER,
    canonical_queue_partition_for_pack,
    normalize_queue_partition,
    resolve_managed_batch_binding,
    resolve_default_local_browser_queue_override,
    resolve_installed_playbook_runner_metadata,
)
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore
from backend.app.services.host_resources.route_identity_projection import (
    build_route_identity_projection,
)
from backend.app.runner.redis_transport_repair import (
    normalize_task_id as _normalize_transport_task_id,
)

logger = logging.getLogger("backend.app.runner.worker")

def _resolve_task_queue_shard(
    pack_id: str, task_ctx: Optional[dict] = None
) -> str:
    binding = resolve_managed_batch_binding(pack_id, task_ctx)
    queue_override = binding.queue_shard if binding else resolve_default_local_browser_queue_override(pack_id, task_ctx)
    if queue_override:
        return queue_override

    if isinstance(task_ctx, dict):
        explicit_queue_shard = normalize_queue_partition(
            task_ctx.get("queue_partition"),
            fallback=None,
        ) or normalize_queue_partition(
            task_ctx.get("queue_shard"),
            fallback=None,
        )
        if explicit_queue_shard:
            return explicit_queue_shard
    metadata = resolve_installed_playbook_runner_metadata(pack_id)
    if metadata:
        metadata_queue_shard = normalize_queue_partition(
            metadata.get("queue_partition"),
            fallback=None,
        ) or normalize_queue_partition(
            metadata.get("queue_shard"),
            fallback=None,
        )
        if metadata_queue_shard:
            return metadata_queue_shard
    return canonical_queue_partition_for_pack(pack_id)


def _build_ready_queue_stores(
    queue_partitions: Optional[list[str] | tuple[str, ...]] = None,
    *,
    queue_store_factory=RedisRunnerQueueStore,
) -> dict[str, RedisRunnerQueueStore]:
    queue_order = list(queue_partitions or RUNNER_READY_QUEUE_ORDER)
    return {
        shard_name: queue_store_factory(pack_id=shard_name)
        for shard_name in queue_order
    }


def _split_ready_target(total_target: int, shard_names: list[str]) -> dict[str, int]:
    if not shard_names:
        return {}
    if total_target <= 0:
        return {shard_name: 0 for shard_name in shard_names}

    base = total_target // len(shard_names)
    remainder = total_target % len(shard_names)
    return {
        shard_name: base + (1 if index < remainder else 0)
        for index, shard_name in enumerate(shard_names)
    }


def _normalize_task_id(raw_value: object) -> str:
    return _normalize_transport_task_id(raw_value)


async def _collect_transport_members(
    queue_stores: list[RedisRunnerQueueStore],
) -> set[str]:
    members: set[str] = set()
    for queue_store in queue_stores:
        client = await queue_store._get_client()
        if not client:
            continue
        pending_members = await client.lrange(queue_store.q_pending, 0, -1)
        temp_members = await client.lrange(queue_store.q_temp, 0, -1)
        processing_members = await client.zrange(queue_store.q_processing, 0, -1)
        delayed_members = await client.zrange(queue_store.q_delayed, 0, -1)
        members.update(_normalize_task_id(item) for item in pending_members)
        members.update(_normalize_task_id(item) for item in temp_members)
        members.update(_normalize_task_id(item) for item in processing_members)
        members.update(_normalize_task_id(item) for item in delayed_members)
    return members


async def _dequeue_from_ready_queues(
    queue_cycle: list[RedisRunnerQueueStore],
    *,
    cursor: int,
    visibility_timeout_sec: int,
    block_timeout_sec: int,
) -> tuple[Optional[str], Optional[RedisRunnerQueueStore], int]:
    if not queue_cycle:
        await asyncio.sleep(block_timeout_sec)
        return None, None, cursor

    cycle_len = len(queue_cycle)

    for offset in range(cycle_len):
        queue_store = queue_cycle[(cursor + offset) % cycle_len]
        task_id = await queue_store.dequeue_task_nowait(
            visibility_timeout_sec=visibility_timeout_sec
        )
        if task_id:
            next_cursor = (cursor + offset + 1) % cycle_len
            return task_id, queue_store, next_cursor

    queue_store = queue_cycle[cursor % cycle_len]
    task_id = await queue_store.dequeue_task_blocking(
        timeout=block_timeout_sec,
        visibility_timeout_sec=visibility_timeout_sec,
    )
    next_cursor = (cursor + 1) % cycle_len
    return task_id, queue_store if task_id else None, next_cursor


async def _repair_misqueued_task_if_needed(
    task_id: str,
    task_data,
    task_queue: RedisRunnerQueueStore,
    *,
    queue_store_factory=RedisRunnerQueueStore,
) -> bool:
    task_ctx = getattr(task_data, "execution_context", None)
    if not isinstance(task_ctx, dict):
        task_ctx = {}
    else:
        task_ctx = dict(task_ctx)
    if getattr(task_data, "queue_shard", None) is not None and not (
        task_ctx.get("queue_partition") or task_ctx.get("queue_shard")
    ):
        task_ctx["queue_shard"] = getattr(task_data, "queue_shard", None)
    pack_id = (
        getattr(task_data, "pack_id", None)
        or task_ctx.get("playbook_code")
        or task_ctx.get("pack_id")
        or ""
    )
    expected_shard = _resolve_task_queue_shard(str(pack_id), task_ctx)
    current_shard = normalize_queue_partition(
        getattr(task_queue, "pack_id", None),
        fallback=DEFAULT_LOCAL_QUEUE_PARTITION,
    )
    if expected_shard == current_shard:
        return False

    target_queue = queue_store_factory(pack_id=expected_shard)
    try:
        enqueued = await target_queue.enqueue_task(
            task_id,
            route_identity=build_route_identity_projection(task_data),
        )
    except TypeError:
        enqueued = await target_queue.enqueue_task(task_id)
    if not enqueued:
        logger.warning(
            "[Worker] Failed to repair misqueued task %s from %s to %s",
            task_id,
            current_shard,
            expected_shard,
        )
        return False

    await task_queue.ack_task(task_id)
    logger.warning(
        "[Worker] Repaired misqueued task %s from %s to %s",
        task_id,
        current_shard,
        expected_shard,
    )
    return True


def _pending_task_runnable_from_queue(task_data) -> bool:
    if getattr(task_data, "status", None) != TaskStatus.PENDING:
        return False
    if getattr(task_data, "blocked_reason", None):
        return False
    return getattr(task_data, "frontier_state", "ready") == "ready"
