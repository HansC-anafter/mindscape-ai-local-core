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
_PGBOUNCER_CODE = """
import json
import psycopg2
from backend.app.runner.db_pool_pressure import get_pgbouncer_admin_url
conn = psycopg2.connect(get_pgbouncer_admin_url(required=True), connect_timeout=5)
conn.autocommit = True
cur = conn.cursor()
cur.execute('SHOW POOLS')
columns = [item[0] for item in cur.description]
rows = [dict(zip(columns, row)) for row in cur.fetchall()]
cur.close()
conn.close()
print(json.dumps({'pools': [row for row in rows if row.get('database') in {'mindscape_core', 'mindscape_vectors'}]}, default=str))
""".strip()


class CalibrationCollector:
    """Collect one bounded evidence sample from existing runtime sources."""

    def __init__(
        self,
        *,
        browser_containers: tuple[str, ...],
        backend_container: str = "mindscape-ai-local-core-backend",
        postgres_container: str = "mindscape-ai-local-core-postgres",
        redis_container: str = "mindscape-ai-local-core-redis",
        command_runner: ReadOnlyCommandRunner | None = None,
        api_client: LocalApiClient | None = None,
        api_base: str = "http://127.0.0.1:8200",
    ) -> None:
        self.browser_containers = browser_containers
        self.backend_container = backend_container
        self.postgres_container = postgres_container
        self.redis_container = redis_container
        self.commands = command_runner or ReadOnlyCommandRunner()
        self.api = api_client or LocalApiClient()
        self.api_base = api_base.rstrip("/")

    def collect_node(self) -> dict[str, Any]:
        meminfo = self._run(
            ["docker", "exec", self.browser_containers[0], "cat", "/proc/meminfo"]
        )
        stats = self._run(
            ["docker", "stats", "--no-stream", "--format", "{{json .}}"]
        )
        cgroups: list[dict[str, Any]] = []
        for container in self.browser_containers:
            current = int(
                self._run(
                    ["docker", "exec", container, "cat", "/sys/fs/cgroup/memory.current"]
                ).strip()
            )
            peak = int(
                self._run(
                    ["docker", "exec", container, "cat", "/sys/fs/cgroup/memory.peak"]
                ).strip()
            )
            events = parse_memory_events(
                self._run(
                    ["docker", "exec", container, "cat", "/sys/fs/cgroup/memory.events"]
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
            ]
        ).strip()
        pgbouncer = json.loads(
            self._run(
                ["docker", "exec", self.backend_container, "python", "-c", _PGBOUNCER_CODE]
            )
        )
        host = self.api.request(
            "GET",
            f"{self.api_base}/api/v1/host-resources/queue-utilization",
        )
        pools = pgbouncer.get("pools") if isinstance(pgbouncer, dict) else []
        return {
            "captured_at_epoch": time.time(),
            "postgres": postgres_raw,
            "pgbouncer_pools": pools if isinstance(pools, list) else [],
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

    def _run(self, argv: list[str]) -> str:
        result = self.commands.run(argv, timeout_seconds=5)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "calibration collector failed")
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
