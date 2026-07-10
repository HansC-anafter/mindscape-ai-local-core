"""Bounded runtime collectors for browser capacity acceptance."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable

from .candidate_plan import summarize_task_candidates
from .commands import ReadOnlyCommandRunner


_SAFE_NAME = re.compile(r"^[a-zA-Z0-9_.-]+$")
_GATE_CODE = (
    "import json; "
    "from backend.app.services.host_resources import get_runner_claim_gate; "
    "print(json.dumps(get_runner_claim_gate(), sort_keys=True))"
)
_METADATA_CODE = (
    "import json; "
    "from backend.app.services.runner_topology import "
    "resolve_installed_playbook_runner_metadata as resolve; "
    "codes=('ig_analyze_following','ig_batch_pin_references','ig_pin_post_detail'); "
    "print(json.dumps({code: resolve(code) for code in codes}, sort_keys=True))"
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
local processing_task_ids = {}
for _, shard in ipairs(ARGV) do
  processing = processing + redis.call('ZCARD', 'mindscape:queue:processing:' .. shard)
  local task_ids = redis.call('ZRANGE', 'mindscape:queue:processing:' .. shard, 0, -1)
  for _, task_id in ipairs(task_ids) do
    table.insert(processing_task_ids, task_id)
  end
end
return cjson.encode({
  policy = cjson.decode(policy_raw),
  reservations = reservations,
  processing_count = processing,
  processing_task_ids = processing_task_ids
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


def parse_runner_partitions(raw: str) -> tuple[str, ...]:
    for line in raw.splitlines():
        if line.startswith("LOCAL_CORE_RUNNER_ACCEPTED_PARTITIONS="):
            value = line.split("=", 1)[1]
            partitions = tuple(
                item.strip() for item in value.split(",") if item.strip()
            )
            if partitions:
                return partitions
    raise ValueError("runner accepted partitions are missing")


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
    playbook_metadata = _run_json(
        command_runner,
        ["docker", "exec", backend, "python", "-c", _METADATA_CODE],
    )

    shard_sql = ",".join(f"'{name}'" for name in shards)
    task_sql = f"""
WITH candidates AS (
  SELECT id AS task_id,
         COALESCE(pack_id, '') AS workload_code,
         status,
         queue_shard,
         COALESCE(concurrency_key, '') AS concurrency_key,
         jsonb_build_object(
           'playbook_code', COALESCE(
             execution_context::jsonb ->> 'playbook_code',
             pack_id,
             ''
           ),
           'workspace_id', COALESCE(
             execution_context::jsonb ->> 'workspace_id',
             workspace_id,
             ''
           ),
           'resource_class', COALESCE(
             execution_context::jsonb ->> 'resource_class',
             ''
           ),
           'inputs', COALESCE(
             execution_context::jsonb -> 'inputs',
             params::jsonb,
             '{{}}'::jsonb
           ),
           'concurrency', COALESCE(
             execution_context::jsonb -> 'concurrency',
             '{{}}'::jsonb
           ),
           'execution_profile', COALESCE(
             execution_context::jsonb -> 'execution_profile',
             '{{}}'::jsonb
           ),
           'resource_requirements', COALESCE(
             execution_context::jsonb -> 'resource_requirements',
             '{{}}'::jsonb
           ),
           'runner_resource_requirements', COALESCE(
             execution_context::jsonb -> 'runner_resource_requirements',
             '{{}}'::jsonb
           )
         ) AS execution_context,
         COALESCE(
           NULLIF(execution_context::jsonb #>> '{{inputs,user_data_dir}}', ''),
           NULLIF(params::jsonb ->> 'user_data_dir', ''),
           ''
         ) AS profile_path,
         runner_id,
         heartbeat_at,
         (
           heartbeat_at IS NOT NULL
           AND heartbeat_at >= NOW() - INTERVAL '90 seconds'
         ) AS heartbeat_fresh,
         frontier_enqueued_at,
         created_at
  FROM tasks
  WHERE queue_shard IN ({shard_sql})
    AND status IN ('pending', 'running')
    AND (
      status = 'running' OR (
        status = 'pending'
        AND frontier_state = 'ready'
        AND COALESCE(blocked_reason, '') = ''
      )
    )
)
SELECT json_build_object(
  'running_count', COUNT(*) FILTER (WHERE status = 'running'),
  'candidates', COALESCE(
    json_agg(
      json_build_object(
        'task_id', task_id,
        'workload_code', workload_code,
        'status', status,
        'queue_shard', queue_shard,
        'concurrency_key', concurrency_key,
        'execution_context', execution_context,
        'profile_path', profile_path,
        'runner_id', runner_id,
        'heartbeat_at', heartbeat_at,
        'heartbeat_fresh', heartbeat_fresh,
        'frontier_enqueued_at', frontier_enqueued_at,
        'created_at', created_at
      ) ORDER BY
        CASE WHEN status = 'running' THEN 0 ELSE 1 END,
        COALESCE(frontier_enqueued_at, created_at),
        created_at,
        task_id
    ),
    '[]'::json
  )
)::text
FROM candidates;
""".strip()
    raw_tasks = _run_json(
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
    processing_task_ids = {
        str(item)
        for item in redis_snapshot.get("processing_task_ids") or []
        if str(item)
    }
    reservation_owner_ids = {
        str(item.get("owner_id") or "")
        for item in redis_snapshot.get("reservations") or []
        if isinstance(item, dict) and str(item.get("owner_id") or "")
    }
    tasks = summarize_task_candidates(
        raw_tasks,
        playbook_metadata=playbook_metadata,
        processing_task_ids=processing_task_ids,
        reservation_owner_ids=reservation_owner_ids,
    )

    runner_slots = 0
    cgroup_limits: list[int] = []
    oom_kill = 0
    oom_group_kill = 0
    runner_evidence: list[dict[str, Any]] = []
    runner_slot_capacity_by_partition: dict[str, int] = {}
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
        partitions = parse_runner_partitions(env_result.stdout)
        events = parse_memory_events(events_result.stdout)
        try:
            cgroup_limit = int(limit_result.stdout.strip())
        except ValueError as exc:
            raise ValueError(f"finite cgroup limit required: {container}") from exc
        if cgroup_limit <= 0:
            raise ValueError(f"positive cgroup limit required: {container}")
        runner_slots += slots
        for partition in partitions:
            runner_slot_capacity_by_partition[partition] = (
                runner_slot_capacity_by_partition.get(partition, 0) + slots
            )
        cgroup_limits.append(cgroup_limit)
        oom_kill += events["oom_kill"]
        oom_group_kill += events["oom_group_kill"]
        runner_evidence.append(
            {
                "container": container,
                "max_inflight": slots,
                "accepted_partitions": list(partitions),
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
        "runner_slot_capacity_by_partition": runner_slot_capacity_by_partition,
        "playbook_metadata": playbook_metadata,
        "browser_cgroup_limit_bytes": max(cgroup_limits),
        "runner_evidence": runner_evidence,
        "oom_kill_count": oom_kill,
        "oom_group_kill_count": oom_group_kill,
    }
