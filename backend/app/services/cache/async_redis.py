"""
Async Redis client singleton for Pub/Sub streaming.

Provides a non-blocking Redis client that can be shared across
MeetingEngine (publish) and SSE generators (subscribe).
Falls back gracefully when Redis is unavailable.
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_async_redis_client = None
_async_redis_lock = asyncio.Lock()


async def get_async_redis_client():
    """Get or create a shared async Redis client.

    Returns None (instead of raising) when Redis is unavailable,
    allowing callers to degrade gracefully to DB-only polling.
    """
    global _async_redis_client

    enabled = os.getenv("REDIS_ENABLED", "true").lower() == "true"
    if not enabled:
        return None

    if _async_redis_client is not None:
        try:
            await _async_redis_client.ping()
            return _async_redis_client
        except Exception:
            _async_redis_client = None

    async with _async_redis_lock:
        # Double-check after acquiring lock
        if _async_redis_client is not None:
            try:
                await _async_redis_client.ping()
                return _async_redis_client
            except Exception:
                _async_redis_client = None

        try:
            from redis.asyncio import Redis

            client = Redis(
                host=os.getenv("REDIS_HOST", "redis"),
                port=int(os.getenv("REDIS_PORT", "6379")),
                password=os.getenv("REDIS_PASSWORD") or None,
                db=int(os.getenv("REDIS_DB", "0")),
                socket_connect_timeout=2,
                socket_timeout=2,
                decode_responses=True,
            )
            await client.ping()
            _async_redis_client = client
            logger.info(
                "[AsyncRedis] Connected to %s:%s",
                os.getenv("REDIS_HOST", "redis"),
                os.getenv("REDIS_PORT", "6379"),
            )
            return client
        except Exception as exc:
            logger.warning(
                "[AsyncRedis] Unavailable, streaming will degrade to DB polling: %s",
                exc,
            )
            return None


def meeting_stream_channel(workspace_id: str) -> str:
    """Return the Redis Pub/Sub channel name for meeting streaming."""
    return f"workspace:{workspace_id}:stream"


async def publish_meeting_chunk(
    workspace_id: str,
    chunk: Dict[str, Any],
) -> bool:
    """Publish a meeting streaming chunk to Redis.

    Returns True if published, False if Redis unavailable (graceful).
    """
    client = await get_async_redis_client()
    if not client:
        return False

    channel = meeting_stream_channel(workspace_id)
    try:
        payload = json.dumps(chunk, ensure_ascii=False)
        await client.publish(channel, payload)
        return True
    except Exception as exc:
        logger.warning("[AsyncRedis] Failed to publish meeting chunk: %s", exc)
        return False


async def subscribe_workspace_stream(workspace_id: str):
    """Subscribe to workspace activity stream via Redis Pub/Sub.

    Yields parsed JSON dicts for each message on the channel.
    Returns (exits) if Redis is unavailable.
    Caller must handle cleanup by breaking out of the generator.
    """
    client = await get_async_redis_client()
    if not client:
        return

    channel = meeting_stream_channel(workspace_id)
    pubsub = client.pubsub()
    await pubsub.subscribe(channel)
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    yield json.loads(message["data"])
                except (json.JSONDecodeError, TypeError):
                    pass  # skip malformed messages
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()


async def psubscribe_all_workspace_streams():
    """Pattern-subscribe to ALL workspace activity streams.

    Uses Redis PSUBSCRIBE ``workspace:*:stream`` to receive events from
    every workspace without needing to enumerate workspace IDs.

    Yields:
        (workspace_id, event_data) tuples.

    Returns (exits) if Redis is unavailable.
    """
    client = await get_async_redis_client()
    if not client:
        return

    pubsub = client.pubsub()
    await pubsub.psubscribe("workspace:*:stream")
    try:
        async for message in pubsub.listen():
            if message["type"] == "pmessage":
                # message["channel"] = "workspace:{id}:stream"
                try:
                    channel = message["channel"]
                    parts = channel.split(":")
                    workspace_id = parts[1] if len(parts) >= 3 else ""
                    event_data = json.loads(message["data"])
                    yield workspace_id, event_data
                except (json.JSONDecodeError, TypeError, IndexError):
                    pass  # skip malformed
    finally:
        await pubsub.punsubscribe("workspace:*:stream")
        await pubsub.close()
