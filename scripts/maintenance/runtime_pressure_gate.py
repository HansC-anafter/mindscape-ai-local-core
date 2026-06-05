#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


DEFAULT_CONTAINERS = [
    "mindscape-ai-local-core-backend",
    "mindscape-ai-local-core-postgres",
    "mindscape-ai-local-core-pgbouncer",
    "mindscape-ai-local-core-runner-default",
    "mindscape-ai-local-core-runner-browser",
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


def collect_task_status_counts(timeout_seconds: float) -> dict[str, Any]:
    sql = (
        "select status, count(*) from tasks "
        "where status in ('running','pending') group by status order by status;"
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


def evaluate_gate(
    task_status: dict[str, Any],
    docker_stats: dict[str, Any],
    endpoint_checks: dict[str, dict[str, Any]],
    thresholds: Thresholds,
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
    task_status = collect_task_status_counts(args.command_timeout_seconds)
    docker_stats = collect_docker_stats(
        DEFAULT_CONTAINERS,
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
    failures = evaluate_gate(
        task_status,
        docker_stats,
        endpoint_checks,
        thresholds,
    )
    payload = {
        "ok": not failures,
        "failures": failures,
        "thresholds": thresholds.__dict__,
        "task_status": task_status,
        "docker_stats": docker_stats,
        "endpoint_checks": endpoint_checks,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
