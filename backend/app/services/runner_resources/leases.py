"""Resource lease stores and key helpers."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any, Iterable, Optional, Protocol

from backend.app.services.stores.redis.runner_queue_store import (
    LUA_COMPARE_AND_DELETE,
    LUA_RENEW_LEASE,
)

LEASE_CONTEXT_KEY = "runner_resource_leases"
LEASE_KEY_PREFIX = "mindscape:runner_resources:lease:v1"


class ResourceLeaseStore(Protocol):
    async def acquire(self, lease_key: str, owner_id: str, ttl_seconds: int) -> bool:
        ...

    async def release(self, lease_key: str, owner_id: str) -> bool:
        ...

    async def extend(self, lease_key: str, owner_id: str, ttl_seconds: int) -> bool:
        ...

    async def list_expired(self, now_epoch: Optional[float] = None) -> list[str]:
        ...


@dataclass(frozen=True)
class ResourceLease:
    lease_key: str
    resource_type: str
    resource_id: str

    def to_context(self) -> dict[str, str]:
        return {
            "lease_key": self.lease_key,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
        }


def _normalize_key_part(value: str) -> str:
    normalized = "".join(
        char if char.isalnum() or char in {"-", "_", "."} else "_"
        for char in str(value or "").strip()
    ).strip("_")
    return normalized[:64] or "default"


def build_resource_lease_key(resource_type: str, resource_id: str) -> str:
    normalized_type = _normalize_key_part(resource_type)
    normalized_id = str(resource_id or "default").strip() or "default"
    digest = hashlib.sha256(normalized_id.encode("utf-8")).hexdigest()[:16]
    label = _normalize_key_part(normalized_id)
    return f"{LEASE_KEY_PREFIX}:{normalized_type}:{label}:{digest}"


def resource_lease_keys_from_context(context: Optional[dict[str, Any]]) -> list[str]:
    if not isinstance(context, dict):
        return []
    raw = context.get(LEASE_CONTEXT_KEY)
    if not isinstance(raw, list):
        return []
    keys: list[str] = []
    seen: set[str] = set()
    for item in raw:
        lease_key = None
        if isinstance(item, dict):
            lease_key = item.get("lease_key")
        elif isinstance(item, str):
            lease_key = item
        if not isinstance(lease_key, str):
            continue
        normalized = lease_key.strip()
        if normalized and normalized not in seen:
            keys.append(normalized)
            seen.add(normalized)
    return keys


async def renew_resource_lease_keys(
    lease_store: ResourceLeaseStore,
    lease_keys: Iterable[str],
    *,
    owner_id: str,
    ttl_seconds: int,
) -> None:
    for lease_key in lease_keys:
        await lease_store.extend(lease_key, owner_id, ttl_seconds)


async def release_resource_lease_keys(
    lease_store: ResourceLeaseStore,
    lease_keys: Iterable[str],
    *,
    owner_id: str,
) -> None:
    for lease_key in lease_keys:
        await lease_store.release(lease_key, owner_id)


class RedisResourceLeaseStore:
    """Redis-backed TTL lease adapter using the existing runner queue client."""

    def __init__(self, redis_queue: Any):
        self._redis_queue = redis_queue

    async def _client(self):
        return await self._redis_queue._get_client()

    async def acquire(self, lease_key: str, owner_id: str, ttl_seconds: int) -> bool:
        client = await self._client()
        if not client:
            return False
        result = await client.set(lease_key, owner_id, nx=True, ex=ttl_seconds)
        return bool(result)

    async def release(self, lease_key: str, owner_id: str) -> bool:
        client = await self._client()
        if not client:
            return False
        result = await client.eval(LUA_COMPARE_AND_DELETE, 1, lease_key, owner_id)
        return bool(result)

    async def extend(self, lease_key: str, owner_id: str, ttl_seconds: int) -> bool:
        client = await self._client()
        if not client:
            return False
        result = await client.eval(LUA_RENEW_LEASE, 1, lease_key, owner_id, ttl_seconds)
        return bool(result)

    async def list_expired(self, now_epoch: Optional[float] = None) -> list[str]:
        return []


class InMemoryResourceLeaseStore:
    """Deterministic lease store for unit tests."""

    def __init__(self, *, now_epoch: float = 0.0):
        self._now_epoch = float(now_epoch)
        self._leases: dict[str, tuple[str, float]] = {}

    def advance(self, seconds: float) -> None:
        self._now_epoch += max(0.0, float(seconds))

    def _now(self, now_epoch: Optional[float] = None) -> float:
        return float(self._now_epoch if now_epoch is None else now_epoch)

    def _purge_expired(self, now_epoch: Optional[float] = None) -> list[str]:
        now = self._now(now_epoch)
        expired = [
            key for key, (_owner, expires_at) in self._leases.items() if expires_at <= now
        ]
        for key in expired:
            self._leases.pop(key, None)
        return expired

    async def acquire(self, lease_key: str, owner_id: str, ttl_seconds: int) -> bool:
        self._purge_expired()
        if lease_key in self._leases:
            return False
        self._leases[lease_key] = (
            str(owner_id),
            self._now() + max(1, int(ttl_seconds or 1)),
        )
        return True

    async def release(self, lease_key: str, owner_id: str) -> bool:
        self._purge_expired()
        entry = self._leases.get(lease_key)
        if not entry or entry[0] != str(owner_id):
            return False
        self._leases.pop(lease_key, None)
        return True

    async def extend(self, lease_key: str, owner_id: str, ttl_seconds: int) -> bool:
        self._purge_expired()
        entry = self._leases.get(lease_key)
        if not entry or entry[0] != str(owner_id):
            return False
        self._leases[lease_key] = (
            str(owner_id),
            self._now() + max(1, int(ttl_seconds or 1)),
        )
        return True

    async def list_expired(self, now_epoch: Optional[float] = None) -> list[str]:
        return self._purge_expired(now_epoch)
