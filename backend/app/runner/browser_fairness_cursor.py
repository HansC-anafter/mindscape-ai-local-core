"""Durable per-shard cursor for browser fairness tie rotation."""

from __future__ import annotations

from typing import Any, Optional


CURSOR_KEY_PREFIX = "mindscape:runner:browser_fair_cursor:v1"
SCAN_CURSOR_KEY_PREFIX = "mindscape:runner:browser_fair_scan_cursor:v1"
CURSOR_TTL_SECONDS = 7 * 24 * 60 * 60


def browser_fairness_cursor_key(queue_shard: str) -> str:
    normalized = str(queue_shard or "").strip()
    if not normalized:
        raise ValueError("queue_shard_required")
    return f"{CURSOR_KEY_PREFIX}:{normalized}"


def browser_fairness_scan_cursor_key(queue_shard: str, queue_name: str) -> str:
    normalized_shard = str(queue_shard or "").strip()
    normalized_queue = str(queue_name or "").strip()
    if not normalized_shard:
        raise ValueError("queue_shard_required")
    if not normalized_queue:
        raise ValueError("queue_name_required")
    return f"{SCAN_CURSOR_KEY_PREFIX}:{normalized_shard}:{normalized_queue}"


async def claim_browser_fairness_scan_offset(
    client: Any,
    *,
    queue_shard: str,
    queue_name: str,
    queue_length: int,
    scan_limit: int,
    ttl_seconds: int = CURSOR_TTL_SECONDS,
) -> int:
    normalized_length = int(queue_length)
    normalized_limit = int(scan_limit)
    if normalized_length <= 0:
        return 0
    if normalized_limit <= 0:
        raise ValueError("scan_limit_must_be_positive")
    if normalized_length <= normalized_limit:
        return 0

    key = browser_fairness_scan_cursor_key(queue_shard, queue_name)
    next_offset = int(await client.incrby(key, normalized_limit))
    await client.expire(
        key,
        max(60, int(ttl_seconds or CURSOR_TTL_SECONDS)),
    )
    return max(0, next_offset - normalized_limit) % normalized_length


async def read_browser_fairness_cursor(
    client: Any,
    *,
    queue_shard: str,
) -> Optional[str]:
    raw = await client.get(browser_fairness_cursor_key(queue_shard))
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    normalized = str(raw or "").strip()
    return normalized or None


async def write_browser_fairness_cursor(
    client: Any,
    *,
    queue_shard: str,
    lane_key: str,
    ttl_seconds: int = CURSOR_TTL_SECONDS,
) -> bool:
    normalized_lane = str(lane_key or "").strip()
    if not normalized_lane:
        return False
    result = await client.setex(
        browser_fairness_cursor_key(queue_shard),
        max(60, int(ttl_seconds or CURSOR_TTL_SECONDS)),
        normalized_lane,
    )
    return bool(result)


__all__ = [
    "CURSOR_KEY_PREFIX",
    "SCAN_CURSOR_KEY_PREFIX",
    "CURSOR_TTL_SECONDS",
    "browser_fairness_cursor_key",
    "browser_fairness_scan_cursor_key",
    "claim_browser_fairness_scan_offset",
    "read_browser_fairness_cursor",
    "write_browser_fairness_cursor",
]
