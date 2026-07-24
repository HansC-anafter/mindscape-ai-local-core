#!/usr/bin/env python3
"""Read-only admission gate for a backend-control-only process reload."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.maintenance.runtime_pressure_gate import fetch_url, run_command
from scripts.maintenance.runtime_pressure_gate_core import (
    collect_pgbouncer_metrics,
    collect_postgres_metrics,
)


_CONTROL_STATE_SQL = """
SELECT json_build_object(
  'active_install_jobs', (
    SELECT count(*)
    FROM capability_install_jobs
    WHERE state IN (
      'queued', 'running', 'waiting_db', 'waiting_db_incident',
      'pending_execution_activation'
    )
  ),
  'incomplete_commit_receipts', (
    SELECT count(*)
    FROM pack_install_commit_receipts
    WHERE projection_state <> 'succeeded'
       OR filesystem_cleanup_state <> 'succeeded'
  ),
  'database_lock_waits', (
    SELECT count(*)
    FROM pg_stat_activity
    WHERE wait_event_type = 'Lock'
  )
);
"""


def collect_control_plane_state(timeout_seconds: float) -> dict[str, Any]:
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
            "-c",
            _CONTROL_STATE_SQL,
        ],
        timeout_seconds,
    )
    if not result.get("ok"):
        return {"ok": False, "error_code": "control_plane_state_unavailable"}
    try:
        state = json.loads(result.get("stdout", "").strip())
    except (TypeError, ValueError):
        return {"ok": False, "error_code": "control_plane_state_invalid"}
    return {"ok": True, "state": state}


def evaluate_backend_control_reload_gate(
    *,
    control_plane_state: dict[str, Any],
    endpoint_checks: dict[str, dict[str, Any]],
    postgres_metrics: dict[str, Any],
    pgbouncer_metrics: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    if not control_plane_state.get("ok"):
        failures.append("control_plane_state_unavailable")
    else:
        state = control_plane_state.get("state") or {}
        if int(state.get("active_install_jobs") or 0) > 0:
            failures.append("active_install_jobs_present")
        if int(state.get("incomplete_commit_receipts") or 0) > 0:
            failures.append("incomplete_commit_receipts_present")
        if int(state.get("database_lock_waits") or 0) > 0:
            failures.append("database_lock_waits_present")

    for label, payload in endpoint_checks.items():
        if not payload.get("ok") or payload.get("status") != 200:
            failures.append(f"{label}_unhealthy")

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
            if (
                int(pool.get("maxwait") or 0) > 0
                or int(pool.get("maxwait_us") or 0) > 0
            ):
                failures.append("pgbouncer_client_maxwait")
    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only gate for reloading backend-control without touching the "
            "execution backend, runners, database, or PgBouncer."
        )
    )
    parser.add_argument("--control-base", default="http://localhost:8220")
    parser.add_argument("--execution-base", default="http://localhost:8200")
    parser.add_argument("--command-timeout-seconds", type=float, default=8.0)
    parser.add_argument("--endpoint-timeout-seconds", type=float, default=5.0)
    parser.add_argument("--pgbouncer-samples", type=int, choices=(3,), default=3)
    parser.add_argument(
        "--pgbouncer-sample-interval-seconds",
        type=float,
        default=2.0,
    )
    parser.add_argument("--output-json", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    control_plane_state = collect_control_plane_state(
        args.command_timeout_seconds
    )
    endpoint_checks = {
        "backend_control": fetch_url(
            f"{args.control_base.rstrip('/')}/health",
            timeout_seconds=args.endpoint_timeout_seconds,
        ),
        "execution_backend": fetch_url(
            f"{args.execution_base.rstrip('/')}/healthz",
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
    failures = evaluate_backend_control_reload_gate(
        control_plane_state=control_plane_state,
        endpoint_checks=endpoint_checks,
        postgres_metrics=postgres_metrics,
        pgbouncer_metrics=pgbouncer_metrics,
    )
    payload = {
        "schema_version": "backend_control_reload_gate.v1",
        "scope": "backend_control_only",
        "gate_pass": not failures,
        "mutation_permit": not failures,
        "failures": failures,
        "execution_workload_gate": "not_applicable_to_control_only_reload",
        "forbidden_targets": [
            "execution_backend",
            "runner",
            "postgres",
            "pgbouncer",
            "frontend",
        ],
        "control_plane_state": control_plane_state,
        "endpoint_checks": endpoint_checks,
        "postgres_metrics": postgres_metrics,
        "pgbouncer_metrics": pgbouncer_metrics,
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
