"""Low-cost Resource Console projection for the runner node byte budget."""

from __future__ import annotations

from typing import Any

from backend.app.services.runner_resources import RedisNodeBudgetStore
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore


def _mb(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, parsed // (1024 * 1024))


async def get_node_budget_projection() -> list[dict[str, Any]]:
    store = RedisNodeBudgetStore(
        RedisRunnerQueueStore(pack_id="default_local_browser")
    )
    try:
        snapshot = await store.snapshot()
    except Exception as exc:
        snapshot = {
            "available": False,
            "degraded_reason": f"node_budget_snapshot_failed:{type(exc).__name__}",
        }
    allocatable = snapshot.get("allocatable_bytes")
    reserved = snapshot.get("reserved_bytes")
    available_bytes = None
    if isinstance(allocatable, int) and isinstance(reserved, int):
        available_bytes = max(0, allocatable - reserved)
    return [
        {
            "budget_id": snapshot.get("budget_id") or "docker_vm_browser_memory",
            "available": bool(snapshot.get("available")),
            "policy_mode": snapshot.get("policy_mode"),
            "policy_fingerprint": snapshot.get("policy_fingerprint"),
            "allocatable_bytes": allocatable,
            "allocatable_mb": _mb(allocatable),
            "reserved_bytes": reserved,
            "reserved_mb": _mb(reserved),
            "available_bytes": available_bytes,
            "available_mb": _mb(available_bytes),
            "active_reservations": int(snapshot.get("active_reservations") or 0),
            "revision": int(snapshot.get("revision") or 0),
            "degraded_reason": snapshot.get("degraded_reason"),
        }
    ]
