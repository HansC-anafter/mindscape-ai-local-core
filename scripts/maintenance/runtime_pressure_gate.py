#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.maintenance.runtime_pressure_gate_core import (
    collect_pgbouncer_metrics,
    collect_postgres_metrics,
    collect_runner_capacity,
)


BASE_CONTAINERS = [
    "mindscape-ai-local-core-backend",
    "mindscape-ai-local-core-postgres",
    "mindscape-ai-local-core-pgbouncer",
]

FALLBACK_RUNNER_CONTAINERS = [
    "mindscape-ai-local-core-runner-default-local-browser",
    "mindscape-ai-local-core-runner-browser",
    "mindscape-ai-local-core-runner-browser-extra",
    "mindscape-ai-local-core-runner-vision",
]


@dataclass(frozen=True)
class Thresholds:
    max_running: int
    max_pending: int
    max_postgres_cpu: float
    max_runner_cpu: float
    max_endpoint_seconds: float


def run_command(args: list[str], timeout_seconds: float) -> dict[str, Any]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            args,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "timeout": True,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "returncode": None,
        }
    return {
        "ok": completed.returncode == 0,
        "timeout": False,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "returncode": completed.returncode,
    }


def parse_percent(raw: str) -> float:
    value = raw.strip().removesuffix("%")
    return float(value or "0")


def fetch_url(url: str, timeout_seconds: float) -> dict[str, Any]:
    started = time.monotonic()
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            body = response.read(4096).decode("utf-8", errors="replace")
            return {
                "ok": 200 <= response.status < 500,
                "status": response.status,
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "body_preview": body[:500],
            }
    except Exception as exc:
        status = exc.code if isinstance(exc, urllib.error.HTTPError) else None
        return {
            "ok": False,
            "status": status,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "error": str(exc),
        }


def collect_task_status_counts(
    timeout_seconds: float,
    *,
    max_running: int,
    max_pending: int,
) -> dict[str, Any]:
    """Count only enough active frontier rows to prove a threshold violation."""

    running_limit = max(0, int(max_running)) + 1
    pending_limit = max(0, int(max_pending)) + 1
    sql = (
        "select status, count(*) from ("
        "(select status from tasks where status = 'running' "
        f"limit {running_limit}) union all "
        "(select status from tasks where status = 'pending' "
        "and task_type in ('playbook_execution', 'tool_execution') "
        "and frontier_state = 'ready' "
        "and (blocked_reason is null or blocked_reason = '') "
        f"limit {pending_limit})"
        ") as bounded_statuses group by status order by status;"
    )
    result = run_command(
        [
            "docker",
            "exec",
            "mindscape-ai-local-core-postgres",
            "psql",
            "-U",
            "mindscape",
            "-d",
            "mindscape_core",
            "-At",
            "-F",
            ",",
            "-c",
            sql,
        ],
        timeout_seconds=timeout_seconds,
    )
    counts = {"pending": 0, "running": 0}
    if result["ok"]:
        for line in result["stdout"].splitlines():
            status, _, raw_count = line.partition(",")
            if status in counts:
                counts[status] = int(raw_count)
    return {
        "ok": result["ok"],
        "counts": counts,
        "pending_semantics": "ready_unblocked_execution_frontier",
        "elapsed_seconds": result["elapsed_seconds"],
        "error": result["stderr"].strip() if not result["ok"] else "",
    }


def collect_docker_stats(
    containers: list[str],
    timeout_seconds: float,
) -> dict[str, Any]:
    result = run_command(
        [
            "docker",
            "stats",
            "--no-stream",
            "--format",
            "{{json .}}",
            *containers,
        ],
        timeout_seconds=timeout_seconds,
    )
    rows: list[dict[str, Any]] = []
    if result["ok"]:
        for line in result["stdout"].splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            item["cpu_percent_value"] = parse_percent(item.get("CPUPerc", "0%"))
            rows.append(item)
    return {
        "ok": result["ok"],
        "rows": rows,
        "elapsed_seconds": result["elapsed_seconds"],
        "error": result["stderr"].strip() if not result["ok"] else "",
    }


def resolve_runtime_stat_containers(
    runner_capacity: dict[str, Any],
) -> list[str]:
    """Return every discovered runner plus the fixed runtime dependencies."""

    discovered = [
        str(row.get("container") or "").strip()
        for row in runner_capacity.get("rows") or []
    ]
    runner_containers = sorted(filter(None, discovered))
    if not runner_containers:
        runner_containers = list(FALLBACK_RUNNER_CONTAINERS)
    return [*BASE_CONTAINERS, *runner_containers]


def evaluate_gate(
    task_status: dict[str, Any],
    docker_stats: dict[str, Any],
    endpoint_checks: dict[str, dict[str, Any]],
    thresholds: Thresholds,
    postgres_metrics: dict[str, Any] | None = None,
    pgbouncer_metrics: dict[str, Any] | None = None,
    runner_capacity: dict[str, Any] | None = None,
) -> list[str]:
    failures: list[str] = []
    counts = task_status.get("counts", {})
    if not task_status.get("ok"):
        failures.append("task_status_unavailable")
    if counts.get("running", 0) > thresholds.max_running:
        failures.append(
            f"running_tasks>{thresholds.max_running}: {counts.get('running', 0)}"
        )
    if counts.get("pending", 0) > thresholds.max_pending:
        failures.append(f"pending_tasks>{thresholds.max_pending}: {counts.get('pending', 0)}")
    if not docker_stats.get("ok"):
        failures.append("docker_stats_unavailable")
    for row in docker_stats.get("rows", []):
        name = row.get("Name", "")
        cpu = row.get("cpu_percent_value", 0.0)
        if name == "mindscape-ai-local-core-postgres" and cpu > thresholds.max_postgres_cpu:
            failures.append(f"postgres_cpu>{thresholds.max_postgres_cpu}: {cpu}")
        if "runner" in name and cpu > thresholds.max_runner_cpu:
            failures.append(f"{name}_cpu>{thresholds.max_runner_cpu}: {cpu}")
    for label, payload in endpoint_checks.items():
        if not payload.get("ok"):
            failures.append(f"{label}_unavailable")
        elif payload.get("elapsed_seconds", 0.0) > thresholds.max_endpoint_seconds:
            failures.append(
                f"{label}_latency>{thresholds.max_endpoint_seconds}: "
                f"{payload.get('elapsed_seconds')}"
            )
    postgres_metrics = postgres_metrics or {"ok": False}
    pgbouncer_metrics = pgbouncer_metrics or {"ok": False}
    runner_capacity = runner_capacity or {"ok": False}
    if not postgres_metrics.get("ok"):
        failures.append("postgres_metrics_unavailable")
    else:
        metrics = postgres_metrics.get("metrics") or {}
        if metrics.get("in_recovery"):
            failures.append("postgres_in_recovery")
        if metrics.get("read_only") != "off":
            failures.append("postgres_read_only")
        if int(metrics.get("invalid_indexes") or 0) > 0:
            failures.append("postgres_invalid_indexes")
        if int(metrics.get("failed_count") or 0) > 0:
            failures.append("postgres_archive_failure")
    if not pgbouncer_metrics.get("ok"):
        failures.append("pgbouncer_metrics_unavailable")
    else:
        if int(pgbouncer_metrics.get("sample_count") or 0) < 3:
            failures.append("pgbouncer_three_samples_required")
        for pool in pgbouncer_metrics.get("rows") or []:
            if int(pool.get("cl_waiting") or 0) > 0:
                failures.append("pgbouncer_client_waiting")
            if int(pool.get("maxwait") or 0) > 0 or int(pool.get("maxwait_us") or 0) > 0:
                failures.append("pgbouncer_client_maxwait")
    if not runner_capacity.get("ok"):
        failures.append("runner_capacity_unavailable")
    elif int(runner_capacity.get("aggregate_max_inflight") or 0) < 7:
        failures.append("runner_capacity_below_7")
    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only runtime pressure gate for local-core deploy/restart decisions.",
    )
    parser.add_argument("--api-base", default="http://localhost:8200")
    parser.add_argument("--max-running", type=int, default=0)
    parser.add_argument("--max-pending", type=int, default=1000)
    parser.add_argument("--max-postgres-cpu", type=float, default=200.0)
    parser.add_argument("--max-runner-cpu", type=float, default=400.0)
    parser.add_argument("--max-endpoint-seconds", type=float, default=5.0)
    parser.add_argument("--command-timeout-seconds", type=float, default=8.0)
    parser.add_argument("--endpoint-timeout-seconds", type=float, default=5.0)
    parser.add_argument("--pgbouncer-samples", type=int, choices=(3,), default=3)
    parser.add_argument(
        "--pgbouncer-sample-interval-seconds",
        type=float,
        default=30.0,
    )
    parser.add_argument("--output-json", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    thresholds = Thresholds(
        max_running=args.max_running,
        max_pending=args.max_pending,
        max_postgres_cpu=args.max_postgres_cpu,
        max_runner_cpu=args.max_runner_cpu,
        max_endpoint_seconds=args.max_endpoint_seconds,
    )
    task_status = collect_task_status_counts(
        args.command_timeout_seconds,
        max_running=thresholds.max_running,
        max_pending=thresholds.max_pending,
    )
    runner_capacity = collect_runner_capacity(
        run_command,
        args.command_timeout_seconds,
    )
    docker_stats = collect_docker_stats(
        resolve_runtime_stat_containers(runner_capacity),
        timeout_seconds=args.command_timeout_seconds,
    )
    api_base = args.api_base.rstrip("/")
    endpoint_checks = {
        "healthz": fetch_url(
            f"{api_base}/healthz",
            timeout_seconds=args.endpoint_timeout_seconds,
        ),
        "active_executions": fetch_url(
            f"{api_base}/api/v1/playbooks/execute/active",
            timeout_seconds=args.endpoint_timeout_seconds,
        ),
    }
    postgres_metrics = collect_postgres_metrics(
        run_command,
        args.command_timeout_seconds,
    )
    pgbouncer_metrics = collect_pgbouncer_metrics(
        run_command,
        args.command_timeout_seconds,
        sample_count=args.pgbouncer_samples,
        sample_interval_seconds=args.pgbouncer_sample_interval_seconds,
    )
    failures = evaluate_gate(
        task_status,
        docker_stats,
        endpoint_checks,
        thresholds,
        postgres_metrics,
        pgbouncer_metrics,
        runner_capacity,
    )
    payload = {
        "ok": not failures,
        "failures": failures,
        "thresholds": thresholds.__dict__,
        "task_status": task_status,
        "docker_stats": docker_stats,
        "endpoint_checks": endpoint_checks,
        "postgres_metrics": postgres_metrics,
        "pgbouncer_metrics": pgbouncer_metrics,
        "runner_capacity": runner_capacity,
    }
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output_json.with_suffix(args.output_json.suffix + ".tmp")
        temporary.write_text(encoded + "\n", encoding="utf-8")
        os.replace(temporary, args.output_json)
    print(encoded)
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
