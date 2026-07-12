"""Bounded node, task, and pool collectors for calibration."""

from __future__ import annotations

import json
import math
import re
import time
from typing import Any

from scripts.maintenance.browser_resource_capacity_preflight_core.commands import (
    ReadOnlyCommandRunner,
)

from .http_client import LocalApiClient
from .parsing import build_node_sample, parse_memory_events


_TASK_ID = re.compile(r"^[0-9a-fA-F-]{36}$")


class CalibrationCommandError(RuntimeError):
    """Preserve the failed read-only command so callers can fail closed by phase."""

    def __init__(self, argv: list[str], returncode: int, stderr: str) -> None:
        self.argv = tuple(argv)
        self.returncode = int(returncode)
        self.stderr = str(stderr or "").strip()
        detail = self.stderr or "empty stderr"
        super().__init__(
            f"calibration command failed ({self.returncode}): "
            f"{' '.join(self.argv)}: {detail}"
        )


_LIVE_BROWSER_OWNERS_LUA = r"""
local cursor = '0'
local result = {}
repeat
  local scanned = redis.call(
    'SCAN', cursor, 'MATCH', 'mindscape:runner_live:task:*', 'COUNT', 100
  )
  cursor = scanned[1]
  for _, key in ipairs(scanned[2]) do
    local raw = redis.call('GET', key)
    if raw then
      local ok, payload = pcall(cjson.decode, raw)
      if ok then
        local shard = tostring(payload.queue_shard or '')
        if shard == 'browser_local'
          or shard == 'ig_browser'
          or shard == 'default_local_browser' then
          table.insert(result, raw)
          if #result >= 10 then return result end
        end
      end
    end
  end
until cursor == '0'
return result
""".strip()
_PGBOUNCER_COLUMNS = (
    "database",
    "user",
    "cl_active",
    "cl_waiting",
    "cl_active_cancel_req",
    "cl_waiting_cancel_req",
    "sv_active",
    "sv_active_cancel",
    "sv_being_canceled",
    "sv_idle",
    "sv_used",
    "sv_tested",
    "sv_login",
    "maxwait",
    "maxwait_us",
    "pool_mode",
    "load_balance_hosts",
)
_PGBOUNCER_ADMIN_URL = (
    "postgresql://mindscape:mindscape_password@127.0.0.1:6432/pgbouncer"
)
_CGROUP_SNAPSHOT_TIMEOUT_SECONDS = 8
_CGROUP_SNAPSHOT_CODE = r"""
import json
from pathlib import Path
root = Path('/sys/fs/cgroup')
def read(name):
    return (root / name).read_text(encoding='utf-8')
events = {
    parts[0]: int(parts[1])
    for line in read('memory.events').splitlines()
    if len(parts := line.split()) == 2
}
stat = {
    parts[0]: int(parts[1])
    for line in read('memory.stat').splitlines()
    if len(parts := line.split()) == 2
}
print(json.dumps({
    'memory_current_bytes': int(read('memory.current').strip()),
    'memory_peak_bytes': int(read('memory.peak').strip()),
    'inactive_file_bytes': int(stat.get('inactive_file') or 0),
    'oom_kill': int(events.get('oom_kill') or 0),
    'oom_group_kill': int(events.get('oom_group_kill') or 0),
}))
""".strip()


def parse_pgbouncer_pools(raw: str) -> list[dict[str, Any]]:
    pools: list[dict[str, Any]] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        values = line.split("|")
        if len(values) != len(_PGBOUNCER_COLUMNS):
            raise ValueError("pgbouncer pool column count mismatch")
        row = dict(zip(_PGBOUNCER_COLUMNS, values))
        if row["database"] in {"mindscape_core", "mindscape_vectors"}:
            pools.append(row)
    return pools


class CalibrationCollector:
    """Collect one bounded evidence sample from existing runtime sources."""

    def __init__(
        self,
        *,
        browser_containers: tuple[str, ...],
        backend_container: str = "mindscape-ai-local-core-backend",
        postgres_container: str = "mindscape-ai-local-core-postgres",
        pgbouncer_container: str = "mindscape-ai-local-core-pgbouncer",
        redis_container: str = "mindscape-ai-local-core-redis",
        command_runner: ReadOnlyCommandRunner | None = None,
        api_client: LocalApiClient | None = None,
        api_base: str = "http://127.0.0.1:8200",
    ) -> None:
        self.browser_containers = browser_containers
        self.backend_container = backend_container
        self.postgres_container = postgres_container
        self.pgbouncer_container = pgbouncer_container
        self.redis_container = redis_container
        self.commands = command_runner or ReadOnlyCommandRunner()
        self.api = api_client or LocalApiClient()
        self.api_base = api_base.rstrip("/")

    def collect_node(
        self,
        *,
        include_all_containers: bool = True,
    ) -> dict[str, Any]:
        meminfo = self._run(
            ["docker", "exec", self.browser_containers[0], "cat", "/proc/meminfo"]
        )
        stats = ""
        if include_all_containers:
            stats = self._run(
                ["docker", "stats", "--no-stream", "--format", "{{json .}}"]
            )
        cgroups: list[dict[str, Any]] = []
        lean_stats: list[str] = []
        for container in self.browser_containers:
            if include_all_containers:
                current = int(
                    self._run(
                        [
                            "docker",
                            "exec",
                            container,
                            "cat",
                            "/sys/fs/cgroup/memory.current",
                        ]
                    ).strip()
                )
                peak = int(
                    self._run(
                        [
                            "docker",
                            "exec",
                            container,
                            "cat",
                            "/sys/fs/cgroup/memory.peak",
                        ]
                    ).strip()
                )
                events = parse_memory_events(
                    self._run(
                        [
                            "docker",
                            "exec",
                            container,
                            "cat",
                            "/sys/fs/cgroup/memory.events",
                        ]
                    )
                )
            else:
                snapshot = json.loads(
                    self._run(
                        [
                            "docker",
                            "exec",
                            container,
                            "python",
                            "-c",
                            _CGROUP_SNAPSHOT_CODE,
                        ],
                        timeout_seconds=_CGROUP_SNAPSHOT_TIMEOUT_SECONDS,
                    )
                )
                current = int(snapshot["memory_current_bytes"])
                peak = int(snapshot["memory_peak_bytes"])
                events = {
                    "oom_kill": int(snapshot["oom_kill"]),
                    "oom_group_kill": int(snapshot["oom_group_kill"]),
                }
                working_set = max(
                    0,
                    current - int(snapshot["inactive_file_bytes"]),
                )
                lean_stats.append(
                    json.dumps(
                        {
                            "Name": container,
                            "MemUsage": f"{working_set}B / {current}B",
                        }
                    )
                )
            cgroups.append(
                {
                    "container": container,
                    "memory_current_bytes": current,
                    "memory_peak_bytes": peak,
                    **events,
                }
            )
        if not include_all_containers:
            stats = "\n".join(lean_stats)
        return build_node_sample(
            captured_at_epoch=time.time(),
            meminfo_raw=meminfo,
            docker_stats_raw=stats,
            browser_containers=self.browser_containers,
            cgroup_rows=cgroups,
        )

    def collect_pool(self) -> dict[str, Any]:
        postgres_raw = self._run(
            [
                "docker",
                "exec",
                self.postgres_container,
                "psql",
                "-U",
                "mindscape",
                "-d",
                "mindscape_core",
                "-Atc",
                "SELECT pg_is_in_recovery(), current_setting('transaction_read_only');",
            ],
            timeout_seconds=15,
        ).strip()
        pgbouncer_raw = self._run(
            [
                "docker",
                "exec",
                self.pgbouncer_container,
                "psql",
                _PGBOUNCER_ADMIN_URL,
                "-w",
                "-Atc",
                "SHOW POOLS",
            ],
            timeout_seconds=15,
        )
        host = self.api.request(
            "GET",
            f"{self.api_base}/api/v1/host-resources/summary?allow_stale=true",
        )
        return {
            "captured_at_epoch": time.time(),
            "postgres": postgres_raw,
            "pgbouncer_pools": parse_pgbouncer_pools(pgbouncer_raw),
            "host_resources_status": host.status,
            "host_resources_elapsed_seconds": host.elapsed_seconds,
        }

    def collect_task(self, task_id: str) -> dict[str, Any]:
        if not _TASK_ID.fullmatch(task_id):
            raise ValueError("task id must be a UUID")
        sql = (
            "SELECT json_build_object("
            "'id', id, 'status', status, 'frontier_state', frontier_state, "
            "'blocked_reason', blocked_reason, 'runner_id', runner_id)::text "
            f"FROM tasks WHERE id = '{task_id}';"
        )
        raw = self._run(
            [
                "docker",
                "exec",
                self.postgres_container,
                "psql",
                "-U",
                "mindscape",
                "-d",
                "mindscape_core",
                "-Atc",
                sql,
            ]
        ).strip()
        return json.loads(raw) if raw else {"id": task_id, "status": "missing"}

    def count_running_browser_tasks(self) -> int:
        sql = (
            "SELECT count(*) FROM tasks WHERE status='running' AND queue_shard IN "
            "('browser_local','ig_browser','default_local_browser');"
        )
        return int(
            self._run(
                [
                    "docker",
                    "exec",
                    self.postgres_container,
                    "psql",
                    "-U",
                    "mindscape",
                    "-d",
                    "mindscape_core",
                    "-Atc",
                    sql,
                ]
            ).strip()
        )

    def list_live_browser_owners(self) -> list[dict[str, Any]]:
        raw = self._run(
            [
                "docker",
                "exec",
                self.redis_container,
                "redis-cli",
                "--raw",
                "EVAL_RO",
                _LIVE_BROWSER_OWNERS_LUA,
                "0",
            ]
        )
        owners: list[dict[str, Any]] = []
        for line in raw.splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                owners.append(payload)
        return owners

    def collect_running_browser_task(self, task_id: str) -> dict[str, Any]:
        if not _TASK_ID.fullmatch(task_id):
            raise ValueError("task id must be a UUID")
        sql = (
            "SELECT json_build_object("
            "'id', id, 'workspace_id', workspace_id, 'pack_id', pack_id, "
            "'status', status, 'queue_shard', queue_shard, "
            "'concurrency_key', concurrency_key, 'runner_id', runner_id, "
            "'started_at_epoch', EXTRACT(EPOCH FROM started_at), "
            "'params', params, 'execution_context', execution_context)::text "
            f"FROM tasks WHERE id = '{task_id}' AND status='running';"
        )
        raw = self._run(
            [
                "docker",
                "exec",
                self.postgres_container,
                "psql",
                "-U",
                "mindscape",
                "-d",
                "mindscape_core",
                "-Atc",
                sql,
            ],
            timeout_seconds=15,
        ).strip()
        payload = json.loads(raw) if raw else {}
        return payload if isinstance(payload, dict) else {}

    def list_running_browser_tasks_started_after(
        self,
        started_after_epoch: float,
    ) -> list[dict[str, Any]]:
        epoch = float(started_after_epoch)
        if not math.isfinite(epoch) or epoch <= 0:
            raise ValueError("observer start epoch must be positive and finite")
        sql = (
            "SELECT json_build_object("
            "'id', id, 'workspace_id', workspace_id, 'pack_id', pack_id, "
            "'status', status, 'queue_shard', queue_shard, "
            "'concurrency_key', concurrency_key, 'runner_id', runner_id, "
            "'started_at_epoch', EXTRACT(EPOCH FROM started_at), "
            "'params', params, 'execution_context', execution_context)::text "
            "FROM tasks WHERE status='running' AND queue_shard IN "
            "('browser_local','ig_browser','default_local_browser') "
            f"AND started_at >= to_timestamp({epoch:.6f}) "
            "ORDER BY started_at ASC, id ASC;"
        )
        raw = self._run(
            [
                "docker",
                "exec",
                self.postgres_container,
                "psql",
                "-U",
                "mindscape",
                "-d",
                "mindscape_core",
                "-Atc",
                sql,
            ]
        )
        return [json.loads(line) for line in raw.splitlines() if line.strip()]

    def read_live_owner(self, task_id: str) -> dict[str, Any]:
        if not _TASK_ID.fullmatch(task_id):
            raise ValueError("task id must be a UUID")
        key = f"mindscape:runner_live:task:{task_id}"
        raw = self._run(
            ["docker", "exec", self.redis_container, "redis-cli", "--raw", "GET", key]
        ).strip()
        ttl_raw = self._run(
            ["docker", "exec", self.redis_container, "redis-cli", "TTL", key]
        ).strip()
        payload = json.loads(raw) if raw else {}
        if not isinstance(payload, dict):
            payload = {}
        payload["ttl_seconds_remaining"] = int(ttl_raw or -2)
        return payload

    def _run(self, argv: list[str], *, timeout_seconds: int = 5) -> str:
        result = self.commands.run(argv, timeout_seconds=timeout_seconds)
        if result.returncode != 0:
            raise CalibrationCommandError(argv, result.returncode, result.stderr)
        return result.stdout


def pool_sample_failures(sample: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if sample.get("postgres") != "f|off":
        failures.append("postgres_not_writable")
    for pool in sample.get("pgbouncer_pools") or []:
        if int(pool.get("cl_waiting") or 0) != 0:
            failures.append("pgbouncer_cl_waiting_nonzero")
        if int(pool.get("maxwait") or 0) != 0:
            failures.append("pgbouncer_maxwait_nonzero")
    if int(sample.get("host_resources_status") or 0) != 200:
        failures.append("host_resources_unavailable")
    if float(sample.get("host_resources_elapsed_seconds") or 0) > 5:
        failures.append("host_resources_latency_above_5s")
    return sorted(set(failures))
