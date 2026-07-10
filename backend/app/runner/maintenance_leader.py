"""Single-owner coordination for runner startup and periodic maintenance."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("backend.app.runner.worker")

MAINTENANCE_LEADER_KEY = "mindscape:runner:maintenance:leader:v1"
MIN_MAINTENANCE_LEASE_SECONDS = 180


def resolve_maintenance_lease_seconds(reap_interval_seconds: int) -> int:
    """Keep one owner across at least three maintenance intervals."""
    return max(
        MIN_MAINTENANCE_LEASE_SECONDS,
        max(1, int(reap_interval_seconds)) * 3,
    )


def maintenance_owner_id(runner_id: str) -> str:
    return f"{str(runner_id).strip()}:maintenance"


def _owner_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore").strip()
    return str(value or "").strip()


async def try_hold_maintenance_leadership(
    redis_queue: Any,
    *,
    runner_id: str,
    ttl_seconds: int,
) -> bool:
    """Acquire or renew the VM-wide leader lease; uncertainty fails closed."""
    owner_id = maintenance_owner_id(runner_id)
    ttl_seconds = max(MIN_MAINTENANCE_LEASE_SECONDS, int(ttl_seconds))
    try:
        acquired = await redis_queue.acquire_lock(
            MAINTENANCE_LEADER_KEY,
            owner_id,
            ttl_seconds,
        )
        if acquired:
            return True

        current_owner = _owner_text(
            await redis_queue.get_lock_owner(MAINTENANCE_LEADER_KEY)
        )
        if current_owner != owner_id:
            return False
        return bool(
            await redis_queue.renew_lock(
                MAINTENANCE_LEADER_KEY,
                owner_id,
                ttl_seconds,
            )
        )
    except Exception as exc:
        logger.warning(
            "Runner maintenance leadership unavailable runner_id=%s error=%s",
            runner_id,
            type(exc).__name__,
        )
        return False
