#!/usr/bin/env python3
"""Read-only admission gate for disruptive local-core process reloads.

This gate is not an admission requirement for ordinary durable capability-pack
install intake. Pack intake has its own control-plane, database-write, incident,
and active-install-job gates.
"""
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
    GateScope,
    collect_pgbouncer_metrics,
    collect_postgres_metrics,
    collect_runner_capacity,
    collect_runner_cpu_pressure,
    collect_task_status_counts as _collect_task_status_counts,
    evaluate_runner_scope,
    parse_percent,
    runner_scope_evidence,
)
from scripts.maintenance.runtime_pressure_gate_core.policy import (
    ALLOWED_ACTIONS,
    RUNTIME_OBSERVATION_ACTION,
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
    running_observation_limit: int
    pending_observation_limit: int
    max_postgres_cpu: float
    max_runner_cpu_ratio: float
    runner_cpu_sample_count: int
    runner_cpu_sustained_sample_count: int
    runner_cpu_sample_interval_seconds: float
    max_endpoint_seconds: float


def _emit_payload(payload: dict[str, Any], output_json: Path | None) -> int:
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_json.with_suffix(output_json.suffix + ".tmp")
        temporary.write_text(encoded + "\n", encoding="utf-8")
        os.replace(temporary, output_json)
    print(encoded)
    return 0 if payload.get("ok") else 2


def _task_status_preflight_failure(
    *,
    task_status: dict[str, Any],
    thresholds: Thresholds,
    scope: GateScope,
) -> dict[str, Any]:
    skipped = {
        "ok": False,
        "skipped": True,
        "reason": "task_status_preflight_failed",
    }
    return {
        "ok": False,
        "failures": ["task_status_unavailable"],
        "gate_stage": "task_status_preflight",
        "thresholds": thresholds.__dict__,
        "task_status": task_status,
        "docker_stats": dict(skipped),
        "endpoint_checks": dict(skipped),
        "postgres_metrics": dict(skipped),
        "pgbouncer_metrics": dict(skipped),
        "runner_capacity": dict(skipped),
        "runner_cpu_pressure": dict(skipped),
        "scope": scope.to_dict(),
    }


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
    running_observation_limit: int,
    pending_observation_limit: int,
) -> dict[str, Any]:
    """Collect bounded workload observations without turning task zero into a gate."""
    return _collect_task_status_counts(
        run_command,
        timeout_seconds,
        running_observation_limit=running_observation_limit,
        pending_observation_limit=pending_observation_limit,
    )


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
    runner_cpu_pressure: dict[str, Any] | None = None,
    scope: GateScope | None = None,
) -> list[str]:
    failures: list[str] = []
    if not task_status.get("ok"):
        failures.append("task_status_unavailable")
    if not docker_stats.get("ok"):
        failures.append("docker_stats_unavailable")
    for row in docker_stats.get("rows", []):
        name = row.get("Name", "")
        cpu = row.get("cpu_percent_value", 0.0)
        if name == "mindscape-ai-local-core-postgres" and cpu > thresholds.max_postgres_cpu:
            failures.append(f"postgres_cpu>{thresholds.max_postgres_cpu}: {cpu}")
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
    else:
        failures.extend(
            evaluate_runner_scope(
                runner_capacity,
                scope or GateScope(),
            )
        )
    runner_cpu_pressure = runner_cpu_pressure or {"collection_ok": False}
    if not runner_cpu_pressure.get("collection_ok"):
        failures.append(
            "runner_cpu_pressure_unavailable:"
            f"{runner_cpu_pressure.get('error_code') or 'unknown'}"
        )
    else:
        failures.extend(
            str(failure)
            for failure in runner_cpu_pressure.get("failures") or []
        )
    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only runtime pressure gate for disruptive local-core process "
            "reload/restart decisions; not for ordinary durable pack install intake."
        ),
    )
    parser.add_argument("--api-base", default="http://localhost:8200")
    parser.add_argument(
        "--running-observation-limit",
        "--max-running",
        dest="running_observation_limit",
        type=int,
        default=100,
        help="Bounded running-task sample size; observational only.",
    )
    parser.add_argument(
        "--pending-observation-limit",
        "--max-pending",
        dest="pending_observation_limit",
        type=int,
        default=1000,
        help="Bounded ready-pending sample size; observational only.",
    )
    parser.add_argument(
        "--action",
        choices=sorted(ALLOWED_ACTIONS),
        default=RUNTIME_OBSERVATION_ACTION,
    )
    parser.add_argument("--target-runner-container")
    parser.add_argument("--allow-sole-owner-target", action="store_true")
    parser.add_argument("--max-postgres-cpu", type=float, default=200.0)
    parser.add_argument("--max-runner-cpu-ratio", type=float, default=0.90)
    parser.add_argument("--runner-cpu-samples", type=int, default=5)
    parser.add_argument(
        "--runner-cpu-sustained-samples",
        type=int,
        default=3,
    )
    parser.add_argument(
        "--runner-cpu-sample-interval-seconds",
        type=float,
        default=2.0,
    )
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
        running_observation_limit=args.running_observation_limit,
        pending_observation_limit=args.pending_observation_limit,
        max_postgres_cpu=args.max_postgres_cpu,
        max_runner_cpu_ratio=args.max_runner_cpu_ratio,
        runner_cpu_sample_count=args.runner_cpu_samples,
        runner_cpu_sustained_sample_count=args.runner_cpu_sustained_samples,
        runner_cpu_sample_interval_seconds=(
            args.runner_cpu_sample_interval_seconds
        ),
        max_endpoint_seconds=args.max_endpoint_seconds,
    )
    scope = GateScope(
        action=args.action,
        target_runner_container=args.target_runner_container,
        allow_sole_owner_target=args.allow_sole_owner_target,
    )
    task_status = collect_task_status_counts(
        args.command_timeout_seconds,
        running_observation_limit=thresholds.running_observation_limit,
        pending_observation_limit=thresholds.pending_observation_limit,
    )
    if not task_status.get("ok"):
        return _emit_payload(
            _task_status_preflight_failure(
                task_status=task_status,
                thresholds=thresholds,
                scope=scope,
            ),
            args.output_json,
        )
    runner_capacity = collect_runner_capacity(
        run_command,
        args.command_timeout_seconds,
    )
    docker_stats = collect_docker_stats(
        resolve_runtime_stat_containers(runner_capacity),
        timeout_seconds=args.command_timeout_seconds,
    )
    runner_cpu_pressure = collect_runner_cpu_pressure(
        run_command,
        [
            str(row.get("container") or "").strip()
            for row in runner_capacity.get("rows") or []
            if str(row.get("container") or "").strip()
        ],
        args.command_timeout_seconds,
        threshold_ratio=thresholds.max_runner_cpu_ratio,
        sample_count=thresholds.runner_cpu_sample_count,
        required_consecutive_samples=(
            thresholds.runner_cpu_sustained_sample_count
        ),
        sample_interval_seconds=(
            thresholds.runner_cpu_sample_interval_seconds
        ),
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
        runner_cpu_pressure,
        scope,
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
        "runner_cpu_pressure": runner_cpu_pressure,
        "scope": runner_scope_evidence(runner_capacity, scope),
    }
    return _emit_payload(payload, args.output_json)


if __name__ == "__main__":
    raise SystemExit(main())
