"""TTL snapshot helpers for runner hot state."""

from __future__ import annotations

import json
import time
from typing import Any, Optional

PROGRESS_SNAPSHOT_TTL_SECONDS = 5
STATUS_SNAPSHOT_TTL_SECONDS = 5
RUN_LOG_COUNT_SNAPSHOT_TTL_SECONDS = 5
SNAPSHOT_KEY_PREFIX = "mindscape:runner_resources:snapshot:v1"


def _normalize_key_part(value: Any) -> str:
    normalized = "".join(
        char if char.isalnum() or char in {"-", "_", "."} else "_"
        for char in str(value or "").strip()
    ).strip("_")
    return normalized[:96] or "default"


def build_progress_snapshot_key(workspace_id: str, execution_id: str) -> str:
    return (
        f"{SNAPSHOT_KEY_PREFIX}:progress:"
        f"{_normalize_key_part(workspace_id)}:{_normalize_key_part(execution_id)}"
    )


def build_status_snapshot_key(execution_id: str) -> str:
    return f"{SNAPSHOT_KEY_PREFIX}:status:{_normalize_key_part(execution_id)}"


def build_run_log_count_snapshot_key(workspace_id: str, execution_id: str) -> str:
    return (
        f"{SNAPSHOT_KEY_PREFIX}:run_log_counts:"
        f"{_normalize_key_part(workspace_id)}:{_normalize_key_part(execution_id)}"
    )


class RedisTtlSnapshotStore:
    def __init__(self, redis_queue: Any):
        self._redis_queue = redis_queue

    async def _client(self):
        return await self._redis_queue._get_client()

    async def set(self, key: str, value: dict[str, Any], ttl_seconds: int) -> bool:
        client = await self._client()
        if not client:
            return False
        await client.set(key, json.dumps(value, separators=(",", ":")), ex=ttl_seconds)
        return True

    async def get(self, key: str) -> Optional[dict[str, Any]]:
        client = await self._client()
        if not client:
            return None
        raw = await client.get(key)
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="ignore")
        try:
            value = json.loads(str(raw))
        except Exception:
            return None
        return value if isinstance(value, dict) else None


class SyncRedisTtlSnapshotStore:
    def __init__(self, cache_service: Any = None):
        self._cache_service = cache_service

    def _cache(self):
        if self._cache_service is not None:
            return self._cache_service
        from backend.app.services.cache.redis_cache import get_cache_service

        return get_cache_service()

    def set(self, key: str, value: dict[str, Any], ttl_seconds: int) -> bool:
        try:
            payload = json.dumps(value, separators=(",", ":"), default=str)
        except Exception:
            return False
        cache = self._cache()
        set_value = getattr(cache, "set", None)
        if not callable(set_value):
            return False
        return bool(set_value(key, payload, max(1, int(ttl_seconds or 1))))

    def get(self, key: str) -> Optional[dict[str, Any]]:
        cache = self._cache()
        get_value = getattr(cache, "get", None)
        if not callable(get_value):
            return None
        raw = get_value(key)
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="ignore")
        try:
            value = json.loads(str(raw))
        except Exception:
            return None
        return value if isinstance(value, dict) else None


class InMemoryTtlSnapshotStore:
    def __init__(self, *, now_epoch: float = 0.0):
        self._now_epoch = float(now_epoch)
        self._values: dict[str, tuple[dict[str, Any], float]] = {}

    def advance(self, seconds: float) -> None:
        self._now_epoch += max(0.0, float(seconds))

    async def set(self, key: str, value: dict[str, Any], ttl_seconds: int) -> bool:
        self._values[key] = (
            dict(value),
            self._now_epoch + max(1, int(ttl_seconds or 1)),
        )
        return True

    async def get(self, key: str) -> Optional[dict[str, Any]]:
        entry = self._values.get(key)
        if not entry:
            return None
        value, expires_at = entry
        if expires_at <= self._now_epoch:
            self._values.pop(key, None)
            return None
        return dict(value)


async def set_ttl_snapshot(
    store: Any,
    key: str,
    value: dict[str, Any],
    *,
    ttl_seconds: int,
) -> bool:
    return bool(await store.set(key, value, max(1, int(ttl_seconds or 1))))


async def get_ttl_snapshot(store: Any, key: str) -> Optional[dict[str, Any]]:
    return await store.get(key)


def set_ttl_snapshot_sync(
    store: Any,
    key: str,
    value: dict[str, Any],
    *,
    ttl_seconds: int,
) -> bool:
    return bool(store.set(key, value, max(1, int(ttl_seconds or 1))))


def get_ttl_snapshot_sync(store: Any, key: str) -> Optional[dict[str, Any]]:
    return store.get(key)


def now_epoch() -> float:
    return time.time()
