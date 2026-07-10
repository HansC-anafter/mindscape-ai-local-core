"""VM-wide byte reservations for browser task admission."""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Protocol

from .node_memory import read_node_memory_snapshot

NODE_BUDGET_CONTEXT_KEY = "runner_node_budget_reservation"
NODE_BUDGET_ID = "docker_vm_browser_memory"
_KEY_PREFIX = "mindscape:runner_resources:node_budget:v1"

_ACQUIRE_LUA = r"""
local reservations_key = KEYS[1]
local expiries_key = KEYS[2]
local total_key = KEYS[3]
local revision_key = KEYS[4]
local policy_key = KEYS[5]
local owner = ARGV[1]
local requested = tonumber(ARGV[2])
local allocatable = tonumber(ARGV[3])
local now_epoch = tonumber(ARGV[4])
local expires_at = tonumber(ARGV[5])
local policy_fingerprint = ARGV[6]
local profile_fingerprint = ARGV[7]
local key_ttl = tonumber(ARGV[8])
local policy_mode = ARGV[9]
local policy_payload = ARGV[10]

redis.call('SET', policy_key, policy_payload)

local expired = redis.call('ZRANGEBYSCORE', expiries_key, '-inf', now_epoch)
local total = tonumber(redis.call('GET', total_key) or '0')
for _, expired_owner in ipairs(expired) do
  local raw = redis.call('HGET', reservations_key, expired_owner)
  if raw then
    local decoded = cjson.decode(raw)
    total = math.max(0, total - tonumber(decoded.bytes or 0))
    redis.call('HDEL', reservations_key, expired_owner)
  end
  redis.call('ZREM', expiries_key, expired_owner)
end

local existing_raw = redis.call('HGET', reservations_key, owner)
if existing_raw then
  local existing = cjson.decode(existing_raw)
  if tonumber(existing.bytes or 0) == requested
    and tostring(existing.policy_fingerprint or '') == policy_fingerprint
    and tostring(existing.resource_profile_fingerprint or '') == profile_fingerprint then
    existing.expires_at_epoch = expires_at
    redis.call('HSET', reservations_key, owner, cjson.encode(existing))
    redis.call('ZADD', expiries_key, expires_at, owner)
    redis.call('SET', total_key, total)
    redis.call('EXPIRE', reservations_key, key_ttl)
    redis.call('EXPIRE', expiries_key, key_ttl)
    redis.call('EXPIRE', total_key, key_ttl)
    redis.call('EXPIRE', revision_key, key_ttl)
    return {1, total, tonumber(existing.revision or 0), cjson.encode(existing)}
  end
  return {-2, total, tonumber(existing.revision or 0), existing_raw}
end

if requested <= 0 or allocatable <= 0 or total + requested > allocatable then
  return {0, total, 0, ''}
end

local revision = tonumber(redis.call('INCR', revision_key))
local reservation = {
  owner_id = owner,
  bytes = requested,
  revision = revision,
  expires_at_epoch = expires_at,
  policy_fingerprint = policy_fingerprint,
  resource_profile_fingerprint = profile_fingerprint,
  allocatable_bytes = allocatable,
  policy_mode = policy_mode
}
total = total + requested
redis.call('HSET', reservations_key, owner, cjson.encode(reservation))
redis.call('ZADD', expiries_key, expires_at, owner)
redis.call('SET', total_key, total)
redis.call('EXPIRE', reservations_key, key_ttl)
redis.call('EXPIRE', expiries_key, key_ttl)
redis.call('EXPIRE', total_key, key_ttl)
redis.call('EXPIRE', revision_key, key_ttl)
return {1, total, revision, cjson.encode(reservation)}
"""

_SNAPSHOT_LUA = r"""
local reservations_key = KEYS[1]
local expiries_key = KEYS[2]
local total_key = KEYS[3]
local revision_key = KEYS[4]
local policy_key = KEYS[5]
local now_epoch = tonumber(ARGV[1])

local expired = redis.call('ZRANGEBYSCORE', expiries_key, '-inf', now_epoch)
local total = tonumber(redis.call('GET', total_key) or '0')
for _, expired_owner in ipairs(expired) do
  local raw = redis.call('HGET', reservations_key, expired_owner)
  if raw then
    local decoded = cjson.decode(raw)
    total = math.max(0, total - tonumber(decoded.bytes or 0))
    redis.call('HDEL', reservations_key, expired_owner)
  end
  redis.call('ZREM', expiries_key, expired_owner)
end
redis.call('SET', total_key, total)

local reservations = redis.call('HVALS', reservations_key)
return {
  total,
  tonumber(redis.call('GET', revision_key) or '0'),
  redis.call('GET', policy_key) or '',
  cjson.encode(reservations)
}
"""

_RENEW_LUA = r"""
local reservations_key = KEYS[1]
local expiries_key = KEYS[2]
local owner = ARGV[1]
local revision = tonumber(ARGV[2])
local expires_at = tonumber(ARGV[3])
local key_ttl = tonumber(ARGV[4])
local raw = redis.call('HGET', reservations_key, owner)
if not raw then return 0 end
local reservation = cjson.decode(raw)
if tonumber(reservation.revision or 0) ~= revision then return 0 end
reservation.expires_at_epoch = expires_at
redis.call('HSET', reservations_key, owner, cjson.encode(reservation))
redis.call('ZADD', expiries_key, expires_at, owner)
redis.call('EXPIRE', reservations_key, key_ttl)
redis.call('EXPIRE', expiries_key, key_ttl)
return 1
"""

_RELEASE_LUA = r"""
local reservations_key = KEYS[1]
local expiries_key = KEYS[2]
local total_key = KEYS[3]
local owner = ARGV[1]
local revision = tonumber(ARGV[2])
local raw = redis.call('HGET', reservations_key, owner)
if not raw then return 0 end
local reservation = cjson.decode(raw)
if tonumber(reservation.revision or 0) ~= revision then return 0 end
local total = tonumber(redis.call('GET', total_key) or '0')
total = math.max(0, total - tonumber(reservation.bytes or 0))
redis.call('HDEL', reservations_key, owner)
redis.call('ZREM', expiries_key, owner)
redis.call('SET', total_key, total)
return 1
"""


@dataclass(frozen=True)
class NodeBudgetPolicy:
    mode: str
    total_bytes: int
    vm_overhead_peak_bytes: int
    non_browser_peak_bytes: int
    allocatable_bytes: int
    fingerprint: str


@dataclass(frozen=True)
class NodeBudgetReservation:
    owner_id: str
    bytes: int
    revision: int
    expires_at_epoch: float
    policy_fingerprint: str
    resource_profile_fingerprint: str
    allocatable_bytes: int
    policy_mode: str

    def to_context(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NodeBudgetAcquireResult:
    allow: bool
    reason: str | None
    reservation: NodeBudgetReservation | None
    reserved_bytes: int
    request_bytes: int
    policy: NodeBudgetPolicy


class NodeBudgetStore(Protocol):
    async def acquire(
        self,
        *,
        owner_id: str,
        request_bytes: int,
        policy: NodeBudgetPolicy,
        profile_fingerprint: str,
        ttl_seconds: int,
    ) -> NodeBudgetAcquireResult: ...

    async def renew(
        self,
        reservation: NodeBudgetReservation,
        *,
        ttl_seconds: int,
    ) -> bool: ...

    async def release(self, reservation: NodeBudgetReservation) -> bool: ...

    async def snapshot(self) -> dict[str, Any]: ...


def _env_mb(name: str, source: Mapping[str, str]) -> int | None:
    raw = source.get(name)
    if raw is None or str(raw).strip() == "":
        return None
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def _fingerprint(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def resource_profile_fingerprint(requirements: Any, request_bytes: int) -> str:
    payload = (
        requirements.to_dict()
        if hasattr(requirements, "to_dict")
        else dict(requirements or {})
    )
    payload["resolved_request_bytes"] = int(request_bytes)
    return _fingerprint(payload)


def resolve_node_budget_policy(
    node_snapshot: Mapping[str, Any],
    *,
    environ: Mapping[str, str] | None = None,
) -> NodeBudgetPolicy | None:
    source = environ if environ is not None else os.environ
    try:
        total_bytes = int(node_snapshot.get("total_bytes") or 0)
        cgroup_limit_bytes = int(node_snapshot.get("cgroup_limit_bytes") or 0)
    except (TypeError, ValueError):
        return None
    if total_bytes <= 0:
        return None

    overhead_mb = _env_mb("LOCAL_CORE_RUNNER_NODE_VM_OVERHEAD_PEAK_MB", source)
    non_browser_mb = _env_mb(
        "LOCAL_CORE_RUNNER_NODE_NON_BROWSER_PEAK_MB",
        source,
    )
    if overhead_mb is not None and non_browser_mb is not None:
        mode = "calibrated"
        overhead_bytes = overhead_mb * 1024 * 1024
        non_browser_bytes = non_browser_mb * 1024 * 1024
    elif 0 < cgroup_limit_bytes <= total_bytes:
        mode = "bootstrap_full_cgroup"
        overhead_bytes = total_bytes - cgroup_limit_bytes
        non_browser_bytes = 0
    else:
        return None

    allocatable = max(0, total_bytes - overhead_bytes - non_browser_bytes)
    payload = {
        "mode": mode,
        "total_bytes": total_bytes,
        "vm_overhead_peak_bytes": overhead_bytes,
        "non_browser_peak_bytes": non_browser_bytes,
        "allocatable_bytes": allocatable,
    }
    return NodeBudgetPolicy(**payload, fingerprint=_fingerprint(payload))


def resolve_browser_request_bytes(
    requirements: Any,
    node_snapshot: Mapping[str, Any],
) -> tuple[int, str] | None:
    try:
        explicit_mb = int(getattr(requirements, "memory_mb", 0) or 0)
    except (TypeError, ValueError):
        explicit_mb = 0
    if explicit_mb > 0:
        return explicit_mb * 1024 * 1024, "playbook_profile"
    try:
        cgroup_limit = int(node_snapshot.get("cgroup_limit_bytes") or 0)
    except (TypeError, ValueError):
        cgroup_limit = 0
    if cgroup_limit > 0:
        return cgroup_limit, "container_limit_fallback"
    return None


def reservation_from_context(
    context: Mapping[str, Any] | None,
) -> NodeBudgetReservation | None:
    if not isinstance(context, Mapping):
        return None
    raw = context.get(NODE_BUDGET_CONTEXT_KEY)
    if not isinstance(raw, Mapping):
        return None
    try:
        return NodeBudgetReservation(
            owner_id=str(raw["owner_id"]),
            bytes=int(raw["bytes"]),
            revision=int(raw["revision"]),
            expires_at_epoch=float(raw["expires_at_epoch"]),
            policy_fingerprint=str(raw["policy_fingerprint"]),
            resource_profile_fingerprint=str(raw["resource_profile_fingerprint"]),
            allocatable_bytes=int(raw["allocatable_bytes"]),
            policy_mode=str(raw["policy_mode"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


class RedisNodeBudgetStore:
    def __init__(self, redis_queue: Any, *, now_fn=time.time):
        self._redis_queue = redis_queue
        self._now_fn = now_fn

    async def _client(self):
        try:
            return await self._redis_queue._get_client()
        except Exception:
            return None

    @property
    def _keys(self) -> tuple[str, str, str, str, str]:
        base = f"{_KEY_PREFIX}:{NODE_BUDGET_ID}"
        return (
            f"{base}:reservations",
            f"{base}:expiries",
            f"{base}:total",
            f"{base}:revision",
            f"{base}:policy",
        )

    async def acquire(
        self,
        *,
        owner_id: str,
        request_bytes: int,
        policy: NodeBudgetPolicy,
        profile_fingerprint: str,
        ttl_seconds: int,
    ) -> NodeBudgetAcquireResult:
        client = await self._client()
        if not client:
            return NodeBudgetAcquireResult(
                False, "node_budget_unavailable", None, 0, request_bytes, policy
            )
        now_epoch = float(self._now_fn())
        expires_at = now_epoch + max(1, int(ttl_seconds))
        try:
            result = await client.eval(
                _ACQUIRE_LUA,
                5,
                *self._keys,
                owner_id,
                int(request_bytes),
                int(policy.allocatable_bytes),
                now_epoch,
                expires_at,
                policy.fingerprint,
                profile_fingerprint,
                max(60, int(ttl_seconds) * 4),
                policy.mode,
                json.dumps(
                    asdict(policy),
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
            code = int(result[0])
            reserved = int(result[1])
        except Exception:
            return NodeBudgetAcquireResult(
                False,
                "node_budget_unavailable",
                None,
                0,
                request_bytes,
                policy,
            )
        if code != 1:
            reason = "node_budget_owner_conflict" if code == -2 else "node_budget_exhausted"
            return NodeBudgetAcquireResult(
                False, reason, None, reserved, request_bytes, policy
            )
        raw_reservation = result[3]
        if isinstance(raw_reservation, bytes):
            raw_reservation = raw_reservation.decode("utf-8")
        payload = json.loads(raw_reservation)
        reservation = NodeBudgetReservation(
            owner_id=str(payload["owner_id"]),
            bytes=int(payload["bytes"]),
            revision=int(payload["revision"]),
            expires_at_epoch=float(payload["expires_at_epoch"]),
            policy_fingerprint=str(payload["policy_fingerprint"]),
            resource_profile_fingerprint=str(
                payload["resource_profile_fingerprint"]
            ),
            allocatable_bytes=int(payload["allocatable_bytes"]),
            policy_mode=str(payload["policy_mode"]),
        )
        return NodeBudgetAcquireResult(
            True, None, reservation, reserved, request_bytes, policy
        )

    async def renew(
        self,
        reservation: NodeBudgetReservation,
        *,
        ttl_seconds: int,
    ) -> bool:
        client = await self._client()
        if not client:
            return False
        expires_at = float(self._now_fn()) + max(1, int(ttl_seconds))
        reservations_key, expiries_key, _total_key, _revision_key, _policy_key = (
            self._keys
        )
        try:
            result = await client.eval(
                _RENEW_LUA,
                2,
                reservations_key,
                expiries_key,
                reservation.owner_id,
                reservation.revision,
                expires_at,
                max(60, int(ttl_seconds) * 4),
            )
            return bool(result)
        except Exception:
            return False

    async def release(self, reservation: NodeBudgetReservation) -> bool:
        client = await self._client()
        if not client:
            return False
        reservations_key, expiries_key, total_key, _revision_key, _policy_key = (
            self._keys
        )
        try:
            result = await client.eval(
                _RELEASE_LUA,
                3,
                reservations_key,
                expiries_key,
                total_key,
                reservation.owner_id,
                reservation.revision,
            )
            return bool(result)
        except Exception:
            return False

    async def snapshot(self) -> dict[str, Any]:
        client = await self._client()
        if not client:
            return {"available": False, "degraded_reason": "node_budget_unavailable"}
        try:
            raw_snapshot = await client.eval(
                _SNAPSHOT_LUA,
                5,
                *self._keys,
                float(self._now_fn()),
            )
        except Exception:
            return {
                "available": False,
                "degraded_reason": "node_budget_snapshot_failed",
            }
        total = int(raw_snapshot[0] or 0)
        revision = int(raw_snapshot[1] or 0)
        raw_policy = raw_snapshot[2]
        if isinstance(raw_policy, bytes):
            raw_policy = raw_policy.decode("utf-8")
        try:
            policy = json.loads(raw_policy) if raw_policy else {}
        except Exception:
            policy = {}
        raw_items_json = raw_snapshot[3]
        if isinstance(raw_items_json, bytes):
            raw_items_json = raw_items_json.decode("utf-8")
        try:
            raw_items = json.loads(raw_items_json) if raw_items_json else []
        except Exception:
            raw_items = []
        reservations: list[dict[str, Any]] = []
        for raw in raw_items or []:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            try:
                reservations.append(json.loads(raw))
            except Exception:
                continue
        return {
            "available": True,
            "budget_id": NODE_BUDGET_ID,
            "reserved_bytes": total,
            "active_reservations": len(reservations),
            "revision": revision,
            "allocatable_bytes": policy.get("allocatable_bytes"),
            "policy_mode": policy.get("mode"),
            "policy_fingerprint": policy.get("fingerprint"),
            "reservations": reservations,
        }


class InMemoryNodeBudgetStore:
    def __init__(self, *, now_epoch: float = 0.0):
        self.now_epoch = float(now_epoch)
        self.revision = 0
        self.reservations: dict[str, NodeBudgetReservation] = {}
        self.policy: NodeBudgetPolicy | None = None

    def advance(self, seconds: float) -> None:
        self.now_epoch += max(0.0, float(seconds))

    def _purge(self) -> None:
        self.reservations = {
            owner: reservation
            for owner, reservation in self.reservations.items()
            if reservation.expires_at_epoch > self.now_epoch
        }

    async def acquire(
        self,
        *,
        owner_id: str,
        request_bytes: int,
        policy: NodeBudgetPolicy,
        profile_fingerprint: str,
        ttl_seconds: int,
    ) -> NodeBudgetAcquireResult:
        self._purge()
        self.policy = policy
        existing = self.reservations.get(owner_id)
        reserved = sum(item.bytes for item in self.reservations.values())
        if existing:
            if (
                existing.bytes != request_bytes
                or existing.policy_fingerprint != policy.fingerprint
                or existing.resource_profile_fingerprint != profile_fingerprint
            ):
                return NodeBudgetAcquireResult(
                    False,
                    "node_budget_owner_conflict",
                    None,
                    reserved,
                    request_bytes,
                    policy,
                )
            refreshed = NodeBudgetReservation(
                **{
                    **asdict(existing),
                    "expires_at_epoch": self.now_epoch + max(1, int(ttl_seconds)),
                }
            )
            self.reservations[owner_id] = refreshed
            return NodeBudgetAcquireResult(
                True, None, refreshed, reserved, request_bytes, policy
            )
        if request_bytes <= 0 or reserved + request_bytes > policy.allocatable_bytes:
            return NodeBudgetAcquireResult(
                False,
                "node_budget_exhausted",
                None,
                reserved,
                request_bytes,
                policy,
            )
        self.revision += 1
        reservation = NodeBudgetReservation(
            owner_id=owner_id,
            bytes=request_bytes,
            revision=self.revision,
            expires_at_epoch=self.now_epoch + max(1, int(ttl_seconds)),
            policy_fingerprint=policy.fingerprint,
            resource_profile_fingerprint=profile_fingerprint,
            allocatable_bytes=policy.allocatable_bytes,
            policy_mode=policy.mode,
        )
        self.reservations[owner_id] = reservation
        return NodeBudgetAcquireResult(
            True,
            None,
            reservation,
            reserved + request_bytes,
            request_bytes,
            policy,
        )

    async def renew(
        self,
        reservation: NodeBudgetReservation,
        *,
        ttl_seconds: int,
    ) -> bool:
        self._purge()
        current = self.reservations.get(reservation.owner_id)
        if not current or current.revision != reservation.revision:
            return False
        self.reservations[reservation.owner_id] = NodeBudgetReservation(
            **{
                **asdict(current),
                "expires_at_epoch": self.now_epoch + max(1, int(ttl_seconds)),
            }
        )
        return True

    async def release(self, reservation: NodeBudgetReservation) -> bool:
        self._purge()
        current = self.reservations.get(reservation.owner_id)
        if not current or current.revision != reservation.revision:
            return False
        self.reservations.pop(reservation.owner_id, None)
        return True

    async def snapshot(self) -> dict[str, Any]:
        self._purge()
        reservations = [item.to_context() for item in self.reservations.values()]
        policy = self.policy
        return {
            "available": True,
            "budget_id": NODE_BUDGET_ID,
            "reserved_bytes": sum(item["bytes"] for item in reservations),
            "active_reservations": len(reservations),
            "revision": self.revision,
            "allocatable_bytes": (
                policy.allocatable_bytes if policy is not None else None
            ),
            "policy_mode": policy.mode if policy is not None else None,
            "policy_fingerprint": (
                policy.fingerprint if policy is not None else None
            ),
            "reservations": reservations,
        }


def current_node_memory_snapshot() -> dict[str, Any]:
    return read_node_memory_snapshot()
