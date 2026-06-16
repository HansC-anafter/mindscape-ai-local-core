"""Snapshot writer orchestration for queue utilization."""

from __future__ import annotations

import os
import time
from typing import Any, Awaitable, Callable

from .queue_utilization_support import (
    SNAPSHOT_WRITER_LEASE_KEY,
    SNAPSHOT_WRITER_LEASE_SECONDS,
)


async def acquire_snapshot_writer_lease(queue_store: Any) -> bool:
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
    store: Any = None,
    default_queue_stores_func: Callable[[], list[Any]],
    acquire_snapshot_writer_lease_func: Callable[[Any], Awaitable[bool]],
    build_live_queue_utilization_func: Callable[..., Awaitable[dict[str, Any]]],
    snapshot_store_cls: Callable[[], Any],
) -> dict[str, Any]:
    stores = queue_stores if queue_stores is not None else default_queue_stores_func()
    if not stores:
        return {"written": False, "reason": "no_queue_stores", "inserted": 0}
    lease_store = stores[0]
    try:
        lease_acquired = await acquire_snapshot_writer_lease_func(lease_store)
    except Exception as exc:
        return {
            "written": False,
            "reason": "lease_unavailable",
            "inserted": 0,
            "error": str(exc),
        }
    if not lease_acquired:
        return {"written": False, "reason": "lease_held", "inserted": 0}

    snapshot = await build_live_queue_utilization_func(
        queue_stores=stores,
        scan_limit=scan_limit,
    )
    snapshot_store = store or snapshot_store_cls()
    inserted = snapshot_store.save_snapshot_batch(snapshot)
    snapshot_store.delete_old_snapshots()
    return {
        "written": True,
        "reason": "lease_acquired",
        "inserted": inserted,
        "snapshot": snapshot,
    }
