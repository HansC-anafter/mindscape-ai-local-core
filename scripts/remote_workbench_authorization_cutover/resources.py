"""Direct Redis resource snapshots for authorization cutover evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from .io import CutoverError, write_private_json, write_private_text


RESOURCE_WINDOWS = frozenset({"06a-infra", "phase06-authorization", "phase06-backout"})
RESOURCE_PHASES = frozenset({"before", "after"})


def resource_snapshot_label(window: str, phase: str) -> str:
    """Return one traversal-safe label from the locked Phase06 window contract."""

    if window not in RESOURCE_WINDOWS or phase not in RESOURCE_PHASES:
        raise CutoverError("Resource snapshot window or phase is not allowed")
    return f"{window}-{phase}"


REDIS_SNAPSHOT_LUA = r"""
local function scan_keys(pattern)
  local cursor = '0'
  local keys = {}
  repeat
    local page = redis.call('SCAN', cursor, 'MATCH', pattern, 'COUNT', 1000)
    cursor = page[1]
    for _, key in ipairs(page[2]) do
      table.insert(keys, key)
    end
  until cursor == '0'
  table.sort(keys)
  return keys
end

local queue_keys = scan_keys('mindscape:queue:*')
local totals = {pending = 0, processing = 0, delayed = 0, deadletter = 0}
local inventory = {}
for _, key in ipairs(queue_keys) do
  local key_type = redis.call('TYPE', key).ok
  table.insert(inventory, key .. '|' .. key_type)
  if string.find(key, 'mindscape:queue:pending:', 1, true) == 1 then
    if key_type ~= 'list' then return redis.error_reply('pending queue type mismatch') end
    totals.pending = totals.pending + redis.call('LLEN', key)
  elseif string.find(key, 'mindscape:queue:processing:', 1, true) == 1 then
    if key_type ~= 'zset' then return redis.error_reply('processing queue type mismatch') end
    totals.processing = totals.processing + redis.call('ZCARD', key)
  elseif string.find(key, 'mindscape:queue:delayed:', 1, true) == 1 then
    if key_type ~= 'zset' then return redis.error_reply('delayed queue type mismatch') end
    totals.delayed = totals.delayed + redis.call('ZCARD', key)
  elseif string.find(key, 'mindscape:queue:deadletter:', 1, true) == 1 then
    if key_type ~= 'list' then return redis.error_reply('deadletter queue type mismatch') end
    totals.deadletter = totals.deadletter + redis.call('LLEN', key)
  end
end

local heartbeat_keys = scan_keys('mindscape:runner_resources:heartbeat:v1:*')
local runners = {count = #heartbeat_keys, capacity = 0, inflight = 0, malformed = 0}
for _, key in ipairs(heartbeat_keys) do
  local raw = redis.call('GET', key)
  local ok, value = pcall(cjson.decode, raw or '')
  if not ok or type(value) ~= 'table' or type(value.capacity) ~= 'table' then
    runners.malformed = runners.malformed + 1
  else
    runners.capacity = runners.capacity + tonumber(value.capacity.max_inflight or 0)
    runners.inflight = runners.inflight + tonumber(value.capacity.inflight or 0)
  end
end

return cjson.encode({totals = totals, inventory = inventory, runners = runners})
""".strip()


class Executor(Protocol):
    """Command interface used by the direct Redis sampler."""

    def run(
        self,
        args: Sequence[str],
        *,
        timeout_seconds: float = 60.0,
        input_text: str | None = None,
    ) -> str:
        """Run a command and return captured stdout."""


@dataclass(frozen=True)
class ResourceSnapshot:
    """Queue and runner state captured from direct Redis commands."""

    totals: dict[str, int]
    inventory: tuple[str, ...]
    runners: dict[str, int]


class RedisResourceSampler:
    """Capture four queue types, full key/type inventory, and runner capacity."""

    def __init__(
        self,
        executor: Executor,
        *,
        redis_container: str = "mindscape-ai-local-core-redis",
    ) -> None:
        self.executor = executor
        self.redis_container = redis_container

    def capture(self) -> ResourceSnapshot:
        """Capture one direct Redis snapshot without using API helpers."""

        raw = self.executor.run(
            [
                "docker",
                "exec",
                self.redis_container,
                "redis-cli",
                "--raw",
                "EVAL",
                REDIS_SNAPSHOT_LUA,
                "0",
            ],
            timeout_seconds=30.0,
        )
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as error:
            raise CutoverError(
                "Direct Redis snapshot returned malformed JSON"
            ) from error
        return self._validate(payload)

    @staticmethod
    def _int_map(value: Any, keys: tuple[str, ...], label: str) -> dict[str, int]:
        if not isinstance(value, Mapping) or set(value) != set(keys):
            raise CutoverError(f"Direct Redis {label} shape mismatch")
        normalized: dict[str, int] = {}
        for key in keys:
            item = value[key]
            if not isinstance(item, int) or item < 0:
                raise CutoverError(f"Direct Redis {label} contains an invalid value")
            normalized[key] = item
        return normalized

    @classmethod
    def _validate(cls, payload: Any) -> ResourceSnapshot:
        if not isinstance(payload, Mapping):
            raise CutoverError("Direct Redis snapshot must be an object")
        totals = cls._int_map(
            payload.get("totals"),
            ("pending", "processing", "delayed", "deadletter"),
            "queue totals",
        )
        runners = cls._int_map(
            payload.get("runners"),
            ("count", "capacity", "inflight", "malformed"),
            "runner snapshot",
        )
        if runners["malformed"] != 0:
            raise CutoverError("Direct Redis runner heartbeat snapshot is malformed")
        inventory = payload.get("inventory")
        if not isinstance(inventory, list) or not all(
            isinstance(item, str) and "|" in item for item in inventory
        ):
            raise CutoverError("Direct Redis queue inventory is malformed")
        normalized_inventory = tuple(sorted(inventory))
        if len(normalized_inventory) != len(set(normalized_inventory)):
            raise CutoverError("Direct Redis queue inventory contains duplicate keys")
        return ResourceSnapshot(
            totals=totals,
            inventory=normalized_inventory,
            runners={
                key: value for key, value in runners.items() if key != "malformed"
            },
        )

    @staticmethod
    def persist(snapshot: ResourceSnapshot, directory: Path, label: str) -> None:
        """Persist a snapshot without emitting queue keys to process output."""

        allowed = {
            resource_snapshot_label(window, phase)
            for window in RESOURCE_WINDOWS
            for phase in RESOURCE_PHASES
        }
        if label not in allowed:
            raise CutoverError("Resource snapshot label is not in the Phase06 contract")
        write_private_json(directory / f"queue-totals-{label}.json", snapshot.totals)
        inventory = "".join(f"{item}\n" for item in snapshot.inventory)
        write_private_text(directory / f"queue-inventory-{label}.txt", inventory)
        write_private_json(directory / f"runner-{label}.json", snapshot.runners)

    @staticmethod
    def compare(before: ResourceSnapshot, after: ResourceSnapshot) -> None:
        """Require zero four-type deltas, identical keys/types, and stable runners."""

        if after.totals["processing"] != 0 or after.runners["inflight"] != 0:
            raise CutoverError(
                "Authorization closure requires zero processing and runner inflight"
            )

        deltas = {
            key: after.totals[key] - before.totals[key]
            for key in ("pending", "processing", "delayed", "deadletter")
        }
        if any(value != 0 for value in deltas.values()):
            raise CutoverError("Authorization window changed direct Redis queue totals")
        if before.inventory != after.inventory:
            raise CutoverError(
                "Authorization window changed Redis queue key/type inventory"
            )
        before_capacity = {
            "count": before.runners["count"],
            "capacity": before.runners["capacity"],
        }
        after_capacity = {
            "count": after.runners["count"],
            "capacity": after.runners["capacity"],
        }
        if before_capacity != after_capacity:
            raise CutoverError("Authorization window changed runner count or capacity")
