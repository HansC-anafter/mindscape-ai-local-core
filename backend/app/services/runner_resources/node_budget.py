"""VM-wide byte reservations for browser task admission."""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from typing import Any

from .node_budget_contract import (
    NODE_BUDGET_CONTEXT_KEY,
    NODE_BUDGET_ID,
    NodeBudgetAcquireResult,
    NodeBudgetPolicy,
    NodeBudgetReservation,
    NodeBudgetStore,
    current_node_memory_snapshot,
    reservation_from_context,
    resolve_browser_request_bytes,
    resolve_node_budget_policy,
    resource_profile_fingerprint,
)
from .node_budget_test_store import InMemoryNodeBudgetStore

_KEY_PREFIX = "mindscape:runner_resources:node_budget:v1"

_RECONCILE_ACTIVE_RESERVATIONS_LUA = r"""
local function extend_collection_ttl(key, key_ttl)
  local current_ttl = redis.call('TTL', key)
  if current_ttl == -1 or (current_ttl >= 0 and current_ttl < key_ttl) then
    redis.call('EXPIRE', key, key_ttl)
  end
end

local function reconcile_active_reservations(
  reservations_key,
  expiries_key,
  total_key,
  revision_key,
  now_epoch
)
  local expired = redis.call('ZRANGEBYSCORE', expiries_key, '-inf', now_epoch)
  for _, expired_owner in ipairs(expired) do
    redis.call('HDEL', reservations_key, expired_owner)
    redis.call('ZREM', expiries_key, expired_owner)
  end

  if redis.call('HLEN', reservations_key) ~= redis.call('ZCARD', expiries_key) then
    error('node_budget_state_cardinality_mismatch')
  end

  local total = 0
  local max_revision = tonumber(redis.call('GET', revision_key) or '0')
  local entries = redis.call('HGETALL', reservations_key)
  for index = 1, #entries, 2 do
    local owner = entries[index]
    local decoded = cjson.decode(entries[index + 1])
    local bytes = tonumber(decoded.bytes or 0)
    local revision = tonumber(decoded.revision or 0)
    if tostring(decoded.owner_id or '') ~= owner then
      error('node_budget_owner_identity_mismatch')
    end
    if not redis.call('ZSCORE', expiries_key, owner) then
      error('node_budget_reservation_expiry_missing')
    end
    if not bytes or bytes <= 0 or not revision or revision <= 0 then
      error('node_budget_reservation_invalid')
    end
    total = total + bytes
    max_revision = math.max(max_revision, revision)
  end

  redis.call('SET', total_key, total)
  if max_revision > tonumber(redis.call('GET', revision_key) or '0') then
    redis.call('SET', revision_key, max_revision)
  end
  return {total, max_revision, #entries / 2}
end
"""

_ACQUIRE_LUA = _RECONCILE_ACTIVE_RESERVATIONS_LUA + r"""
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

local reconciled = reconcile_active_reservations(
  reservations_key,
  expiries_key,
  total_key,
  revision_key,
  now_epoch
)
local total = tonumber(reconciled[1])
redis.call('SET', policy_key, policy_payload)

local existing_raw = redis.call('HGET', reservations_key, owner)
if existing_raw then
  local existing = cjson.decode(existing_raw)
  if tonumber(existing.bytes or 0) == requested
    and tostring(existing.policy_fingerprint or '') == policy_fingerprint
    and tostring(existing.resource_profile_fingerprint or '') == profile_fingerprint then
    existing.expires_at_epoch = expires_at
    redis.call('HSET', reservations_key, owner, cjson.encode(existing))
    redis.call('ZADD', expiries_key, expires_at, owner)
    extend_collection_ttl(reservations_key, key_ttl)
    extend_collection_ttl(expiries_key, key_ttl)
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
extend_collection_ttl(reservations_key, key_ttl)
extend_collection_ttl(expiries_key, key_ttl)
return {1, total, revision, cjson.encode(reservation)}
"""

_SNAPSHOT_LUA = _RECONCILE_ACTIVE_RESERVATIONS_LUA + r"""
local reservations_key = KEYS[1]
local expiries_key = KEYS[2]
local total_key = KEYS[3]
local revision_key = KEYS[4]
local policy_key = KEYS[5]
local now_epoch = tonumber(ARGV[1])

local reconciled = reconcile_active_reservations(
  reservations_key,
  expiries_key,
  total_key,
  revision_key,
  now_epoch
)
local reservations = redis.call('HVALS', reservations_key)
return {
  tonumber(reconciled[1]),
  tonumber(redis.call('GET', revision_key) or '0'),
  redis.call('GET', policy_key) or '',
  cjson.encode(reservations)
}
"""

_RENEW_LUA = _RECONCILE_ACTIVE_RESERVATIONS_LUA + r"""
local reservations_key = KEYS[1]
local expiries_key = KEYS[2]
local total_key = KEYS[3]
local revision_key = KEYS[4]
local owner = ARGV[1]
local revision = tonumber(ARGV[2])
local expires_at = tonumber(ARGV[3])
local key_ttl = tonumber(ARGV[4])
local now_epoch = tonumber(ARGV[5])
reconcile_active_reservations(
  reservations_key,
  expiries_key,
  total_key,
  revision_key,
  now_epoch
)
local raw = redis.call('HGET', reservations_key, owner)
if not raw then return 0 end
local reservation = cjson.decode(raw)
if tonumber(reservation.revision or 0) ~= revision then return 0 end
reservation.expires_at_epoch = expires_at
redis.call('HSET', reservations_key, owner, cjson.encode(reservation))
redis.call('ZADD', expiries_key, expires_at, owner)
extend_collection_ttl(reservations_key, key_ttl)
extend_collection_ttl(expiries_key, key_ttl)
return 1
"""

_RECONCILE_DOWN_LUA = _RECONCILE_ACTIVE_RESERVATIONS_LUA + r"""
local reservations_key = KEYS[1]
local expiries_key = KEYS[2]
local total_key = KEYS[3]
local revision_key = KEYS[4]
local owner = ARGV[1]
local revision = tonumber(ARGV[2])
local requested = tonumber(ARGV[3])
local evidence_fingerprint = ARGV[4]
local reconciled_at_epoch = tonumber(ARGV[5])
local reconciled = reconcile_active_reservations(
  reservations_key,
  expiries_key,
  total_key,
  revision_key,
  reconciled_at_epoch
)
local raw = redis.call('HGET', reservations_key, owner)
if not raw then return 0 end
local reservation = cjson.decode(raw)
if tonumber(reservation.revision or 0) ~= revision then return -1 end
local existing = tonumber(reservation.bytes or 0)
if requested <= 0 or requested >= existing then return -2 end
if tostring(evidence_fingerprint or '') == '' then return -3 end
local total = tonumber(reconciled[1])
reservation.bytes = requested
reservation.reconciled_from_bytes = existing
reservation.reconciliation_evidence_fingerprint = evidence_fingerprint
reservation.reconciled_at_epoch = reconciled_at_epoch
total = math.max(0, total - (existing - requested))
redis.call('HSET', reservations_key, owner, cjson.encode(reservation))
redis.call('SET', total_key, total)
return 1
"""

_RELEASE_LUA = _RECONCILE_ACTIVE_RESERVATIONS_LUA + r"""
local reservations_key = KEYS[1]
local expiries_key = KEYS[2]
local total_key = KEYS[3]
local revision_key = KEYS[4]
local owner = ARGV[1]
local revision = tonumber(ARGV[2])
local now_epoch = tonumber(ARGV[3])
local reconciled = reconcile_active_reservations(
  reservations_key,
  expiries_key,
  total_key,
  revision_key,
  now_epoch
)
local raw = redis.call('HGET', reservations_key, owner)
if not raw then return 0 end
local reservation = cjson.decode(raw)
if tonumber(reservation.revision or 0) ~= revision then return 0 end
local total = tonumber(reconciled[1])
total = math.max(0, total - tonumber(reservation.bytes or 0))
redis.call('HDEL', reservations_key, owner)
redis.call('ZREM', expiries_key, owner)
redis.call('SET', total_key, total)
return 1
"""


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
        now_epoch = float(self._now_fn())
        expires_at = now_epoch + max(1, int(ttl_seconds))
        reservations_key, expiries_key, total_key, revision_key, _policy_key = self._keys
        try:
            result = await client.eval(
                _RENEW_LUA,
                4,
                reservations_key,
                expiries_key,
                total_key,
                revision_key,
                reservation.owner_id,
                reservation.revision,
                expires_at,
                max(60, int(ttl_seconds) * 4),
                now_epoch,
            )
            return bool(result)
        except Exception:
            return False

    async def reconcile_down(
        self,
        reservation: NodeBudgetReservation,
        *,
        request_bytes: int,
        evidence_fingerprint: str,
    ) -> bool:
        client = await self._client()
        if not client:
            return False
        reservations_key, expiries_key, total_key, revision_key, _policy_key = self._keys
        try:
            result = await client.eval(
                _RECONCILE_DOWN_LUA,
                4,
                reservations_key,
                expiries_key,
                total_key,
                revision_key,
                reservation.owner_id,
                reservation.revision,
                int(request_bytes),
                str(evidence_fingerprint or ""),
                float(self._now_fn()),
            )
            return int(result) == 1
        except Exception:
            return False

    async def release(self, reservation: NodeBudgetReservation) -> bool:
        client = await self._client()
        if not client:
            return False
        reservations_key, expiries_key, total_key, revision_key, _policy_key = self._keys
        try:
            result = await client.eval(
                _RELEASE_LUA,
                4,
                reservations_key,
                expiries_key,
                total_key,
                revision_key,
                reservation.owner_id,
                reservation.revision,
                float(self._now_fn()),
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
