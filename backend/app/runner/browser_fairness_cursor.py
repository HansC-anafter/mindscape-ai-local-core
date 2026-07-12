"""Durable per-shard cursor for browser fairness tie rotation."""

from __future__ import annotations

from typing import Any, Optional


CURSOR_KEY_PREFIX = "mindscape:runner:browser_fair_cursor:v1"
CURSOR_TTL_SECONDS = 7 * 24 * 60 * 60


def browser_fairness_cursor_key(queue_shard: str) -> str:
    normalized = str(queue_shard or "").strip()
    if not normalized:
        raise ValueError("queue_shard_required")
    return f"{CURSOR_KEY_PREFIX}:{normalized}"


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
    "CURSOR_TTL_SECONDS",
    "browser_fairness_cursor_key",
    "read_browser_fairness_cursor",
    "write_browser_fairness_cursor",
]
