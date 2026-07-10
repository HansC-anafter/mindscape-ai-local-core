"""Single-owner coordination for runner startup and periodic maintenance."""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("backend.app.runner.worker")

MAINTENANCE_LEADER_KEY = "mindscape:runner:maintenance:leader:v1"
PARTITION_MAINTENANCE_LEADER_KEY_PREFIX = (
    "mindscape:runner:maintenance:partition"
)
MIN_MAINTENANCE_LEASE_SECONDS = 180
_QUEUE_PARTITION_PATTERN = re.compile(r"^[a-z0-9_-]+$")


def resolve_maintenance_lease_seconds(reap_interval_seconds: int) -> int:
    """Keep one owner across at least three maintenance intervals."""
    return max(
        MIN_MAINTENANCE_LEASE_SECONDS,
        max(1, int(reap_interval_seconds)) * 3,
    )


def maintenance_owner_id(runner_id: str) -> str:
    return f"{str(runner_id).strip()}:maintenance"


def partition_maintenance_leader_key(queue_partition: str) -> str:
    partition = str(queue_partition or "").strip()
    if not _QUEUE_PARTITION_PATTERN.fullmatch(partition):
        raise ValueError("queue_partition must be a canonical partition code")
    return f"{PARTITION_MAINTENANCE_LEADER_KEY_PREFIX}:{partition}:leader:v1"


def partition_maintenance_owner_id(
    runner_id: str,
    queue_partition: str,
) -> str:
    partition = str(queue_partition or "").strip()
    partition_maintenance_leader_key(partition)
    return f"{maintenance_owner_id(runner_id)}:{partition}"


def _owner_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore").strip()
    return str(value or "").strip()


async def _try_hold_maintenance_lease(
    redis_queue: Any,
    *,
    lease_key: str,
    owner_id: str,
    runner_id: str,
    ttl_seconds: int,
    scope: str,
) -> bool:
    ttl_seconds = max(MIN_MAINTENANCE_LEASE_SECONDS, int(ttl_seconds))
    try:
        acquired = await redis_queue.acquire_lock(
            lease_key,
            owner_id,
            ttl_seconds,
        )
        if acquired:
            return True

        current_owner = _owner_text(
            await redis_queue.get_lock_owner(lease_key)
        )
        if current_owner != owner_id:
            return False
        return bool(
            await redis_queue.renew_lock(
                lease_key,
                owner_id,
                ttl_seconds,
            )
        )
    except Exception as exc:
        logger.warning(
            "Runner maintenance leadership unavailable "
            "runner_id=%s scope=%s error=%s",
            runner_id,
            scope,
            type(exc).__name__,
        )
        return False


async def try_hold_maintenance_leadership(
    redis_queue: Any,
    *,
    runner_id: str,
    ttl_seconds: int,
) -> bool:
    """Acquire or renew the VM-wide global-chores lease."""
    return await _try_hold_maintenance_lease(
        redis_queue,
        lease_key=MAINTENANCE_LEADER_KEY,
        owner_id=maintenance_owner_id(runner_id),
        runner_id=runner_id,
        ttl_seconds=ttl_seconds,
        scope="global",
    )


async def try_hold_partition_maintenance_leadership(
    redis_queue: Any,
    *,
    runner_id: str,
    queue_partition: str,
    ttl_seconds: int,
) -> bool:
    """Acquire or renew one queue partition's release-owner lease."""
    try:
        lease_key = partition_maintenance_leader_key(queue_partition)
        owner_id = partition_maintenance_owner_id(runner_id, queue_partition)
    except ValueError:
        logger.warning(
            "Runner partition maintenance leadership rejected "
            "runner_id=%s queue_partition=%r",
            runner_id,
            queue_partition,
        )
        return False
    return await _try_hold_maintenance_lease(
        redis_queue,
        lease_key=lease_key,
        owner_id=owner_id,
        runner_id=runner_id,
        ttl_seconds=ttl_seconds,
        scope=f"partition:{queue_partition}",
    )
