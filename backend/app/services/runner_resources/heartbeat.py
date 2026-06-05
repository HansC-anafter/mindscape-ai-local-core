"""Runner resource heartbeat snapshots."""

from __future__ import annotations

import time
from typing import Any

from .snapshots import RedisTtlSnapshotStore

RUNNER_RESOURCE_HEARTBEAT_TTL_SECONDS = 30
HEARTBEAT_KEY_PREFIX = "mindscape:runner_resources:heartbeat:v1"


def _heartbeat_key(runner_id: str) -> str:
    return f"{HEARTBEAT_KEY_PREFIX}:{str(runner_id or '').strip()}"


def build_runner_resource_heartbeat(
    *,
    runner_id: str,
    profile_code: str,
    queue_shards: list[str] | tuple[str, ...],
    capacity: Any,
    resource_snapshot: dict[str, Any] | None,
    claim_control: dict[str, Any] | None = None,
    now_epoch: float | None = None,
) -> dict[str, Any]:
    captured_at = float(now_epoch if now_epoch is not None else time.time())
    return {
        "version": 1,
        "runner_id": runner_id,
        "profile_code": profile_code,
        "queue_shards": [str(item) for item in queue_shards],
        "captured_at_epoch": captured_at,
        "capacity": {
            "max_inflight": int(getattr(capacity, "max_inflight", 0) or 0),
            "inflight": int(getattr(capacity, "inflight", 0) or 0),
            "available_slots": int(getattr(capacity, "available_slots", 0) or 0),
            "poll_batch_limit": int(getattr(capacity, "poll_batch_limit", 0) or 0),
            "saturated": bool(getattr(capacity, "saturated", False)),
        },
        "resource_snapshot": resource_snapshot or {},
        "claim_control": claim_control or {
            "mode": "active",
            "claim_enabled": True,
            "source": "default",
        },
    }


async def publish_runner_resource_heartbeat(
    redis_queue: Any,
    heartbeat: dict[str, Any],
    *,
    ttl_seconds: int = RUNNER_RESOURCE_HEARTBEAT_TTL_SECONDS,
) -> bool:
    runner_id = str(heartbeat.get("runner_id") or "").strip()
    if not runner_id:
        return False
    return await RedisTtlSnapshotStore(redis_queue).set(
        _heartbeat_key(runner_id),
        heartbeat,
        ttl_seconds,
    )


async def list_active_runner_resource_heartbeats(
    redis_queue: Any,
    *,
    now_epoch: float | None = None,
) -> list[dict[str, Any]]:
    client = await redis_queue._get_client()
    if not client:
        return []
    now = float(now_epoch if now_epoch is not None else time.time())
    heartbeats: list[dict[str, Any]] = []
    async for key in client.scan_iter(match=f"{HEARTBEAT_KEY_PREFIX}:*"):
        raw = await RedisTtlSnapshotStore(redis_queue).get(key)
        if not isinstance(raw, dict):
            continue
        captured_at = raw.get("captured_at_epoch")
        if isinstance(captured_at, (int, float)) and now - float(captured_at) <= RUNNER_RESOURCE_HEARTBEAT_TTL_SECONDS:
            heartbeats.append(raw)
    return heartbeats
