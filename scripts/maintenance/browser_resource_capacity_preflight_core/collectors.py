"""Bounded runtime collectors for browser capacity acceptance."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable

from .commands import ReadOnlyCommandRunner


_SAFE_NAME = re.compile(r"^[a-zA-Z0-9_.-]+$")
_GATE_CODE = (
    "import json; "
    "from backend.app.services.host_resources import get_runner_claim_gate; "
    "print(json.dumps(get_runner_claim_gate(), sort_keys=True))"
)
_REDIS_SCRIPT = """
local base = 'mindscape:runner_resources:node_budget:v1:docker_vm_browser_memory'
local policy_raw = redis.call('GET', base .. ':policy') or '{}'
local reservations_raw = redis.call('HVALS', base .. ':reservations')
local reservations = {}
for _, raw in ipairs(reservations_raw) do
  table.insert(reservations, cjson.decode(raw))
end
local processing = 0
for _, shard in ipairs(ARGV) do
  processing = processing + redis.call('ZCARD', 'mindscape:queue:processing:' .. shard)
end
return cjson.encode({
  policy = cjson.decode(policy_raw),
  reservations = reservations,
  processing_count = processing
})
""".strip()


@dataclass(frozen=True)
class RuntimeTargets:
    backend_container: str
    postgres_container: str
    redis_container: str
    runner_containers: tuple[str, ...]
    queue_shards: tuple[str, ...]


def _require_safe_names(values: Iterable[str]) -> tuple[str, ...]:
    names = tuple(str(value).strip() for value in values if str(value).strip())
    if not names or any(not _SAFE_NAME.fullmatch(name) for name in names):
        raise ValueError("container and queue names must be non-empty safe identifiers")
    return names


def parse_meminfo(raw: str) -> dict[str, int]:
    values: dict[str, int] = {}
    for line in raw.splitlines():
        match = re.fullmatch(r"(MemTotal|MemAvailable):\s+(\d+)\s+kB", line.strip())
        if match:
            values[match.group(1)] = int(match.group(2)) * 1024
    if set(values) != {"MemTotal", "MemAvailable"}:
        raise ValueError("MemTotal and MemAvailable are required")
    return {
        "total_bytes": values["MemTotal"],
        "available_bytes": values["MemAvailable"],
    }


def parse_memory_events(raw: str) -> dict[str, int]:
    values: dict[str, int] = {}
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].isdigit():
            values[parts[0]] = int(parts[1])
    return {
        "oom_kill": values.get("oom_kill", 0),
        "oom_group_kill": values.get("oom_group_kill", 0),
    }


def parse_runner_max_inflight(raw: str) -> int:
    for line in raw.splitlines():
        if line.startswith("LOCAL_CORE_RUNNER_MAX_INFLIGHT="):
            return max(0, int(line.split("=", 1)[1]))
    raise ValueError("runner max_inflight is missing")


def _run_json(runner: ReadOnlyCommandRunner, argv: list[str]) -> dict[str, Any]:
    result = runner.run(argv)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "runtime collector failed")
    payload = json.loads(result.stdout.strip())
    if not isinstance(payload, dict):
        raise ValueError("collector output must be an object")
    return payload


def collect_runtime_snapshot(
    command_runner: ReadOnlyCommandRunner,
    targets: RuntimeTargets,
) -> dict[str, Any]:
    runners = _require_safe_names(targets.runner_containers)
    shards = _require_safe_names(targets.queue_shards)
    backend = _require_safe_names([targets.backend_container])[0]
    postgres = _require_safe_names([targets.postgres_container])[0]
    redis = _require_safe_names([targets.redis_container])[0]

    gate = _run_json(
        command_runner,
        ["docker", "exec", backend, "python", "-c", _GATE_CODE],
    )
    redis_snapshot = _run_json(
        command_runner,
        [
            "docker",
            "exec",
            redis,
            "redis-cli",
            "--raw",
            "EVAL_RO",
            _REDIS_SCRIPT,
            "0",
            *shards,
        ],
    )

    shard_sql = ",".join(f"'{name}'" for name in shards)
    task_sql = f"""
WITH candidates AS (
  SELECT status, frontier_state, COALESCE(blocked_reason, '') AS blocked_reason,
         COALESCE(concurrency_key, '') AS lock_key
  FROM tasks
  WHERE queue_shard IN ({shard_sql})
    AND status IN ('pending', 'running')
), running_locks AS (
  SELECT lock_key, COUNT(*) AS item_count
  FROM candidates
  WHERE status = 'running' AND lock_key <> ''
  GROUP BY lock_key
)
SELECT json_build_object(
  'running_count', COUNT(*) FILTER (WHERE status = 'running'),
  'running_distinct_locks', COUNT(DISTINCT lock_key) FILTER (
    WHERE status = 'running' AND lock_key <> ''
  ),
  'runnable_distinct_locks', COUNT(DISTINCT lock_key) FILTER (
    WHERE lock_key <> '' AND (
      status = 'running' OR (
        status = 'pending' AND frontier_state = 'ready' AND blocked_reason = ''
      )
    )
  ),
  'duplicate_running_lock_count', (
    SELECT COUNT(*) FROM running_locks WHERE item_count > 1
  )
)::text
FROM candidates;
""".strip()
    tasks = _run_json(
        command_runner,
        [
            "docker",
            "exec",
            postgres,
            "psql",
            "-U",
            "mindscape",
            "-d",
            "mindscape_core",
            "-Atc",
            task_sql,
        ],
    )

    runner_slots = 0
    cgroup_limits: list[int] = []
    oom_kill = 0
    oom_group_kill = 0
    runner_evidence: list[dict[str, Any]] = []
    for container in runners:
        env_result = command_runner.run(["docker", "exec", container, "env"])
        events_result = command_runner.run(
            [
                "docker",
                "exec",
                container,
                "cat",
                "/sys/fs/cgroup/memory.events",
            ]
        )
        limit_result = command_runner.run(
            [
                "docker",
                "exec",
                container,
                "cat",
                "/sys/fs/cgroup/memory.max",
            ]
        )
        if (
            env_result.returncode != 0
            or events_result.returncode != 0
            or limit_result.returncode != 0
        ):
            raise RuntimeError(f"runner evidence unavailable: {container}")
        slots = parse_runner_max_inflight(env_result.stdout)
        events = parse_memory_events(events_result.stdout)
        try:
            cgroup_limit = int(limit_result.stdout.strip())
        except ValueError as exc:
            raise ValueError(f"finite cgroup limit required: {container}") from exc
        if cgroup_limit <= 0:
            raise ValueError(f"positive cgroup limit required: {container}")
        runner_slots += slots
        cgroup_limits.append(cgroup_limit)
        oom_kill += events["oom_kill"]
        oom_group_kill += events["oom_group_kill"]
        runner_evidence.append(
            {
                "container": container,
                "max_inflight": slots,
                "cgroup_limit_bytes": cgroup_limit,
                **events,
            }
        )

    mem_result = command_runner.run(
        ["docker", "exec", runners[0], "cat", "/proc/meminfo"]
    )
    if mem_result.returncode != 0:
        raise RuntimeError("node memory evidence unavailable")

    return {
        "claim_gate": gate,
        "node_budget": redis_snapshot,
        "tasks": tasks,
        "memory": parse_meminfo(mem_result.stdout),
        "runner_slot_capacity": runner_slots,
        "browser_cgroup_limit_bytes": max(cgroup_limits),
        "runner_evidence": runner_evidence,
        "oom_kill_count": oom_kill,
        "oom_group_kill_count": oom_group_kill,
    }
