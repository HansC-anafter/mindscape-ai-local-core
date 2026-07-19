"""Strict observer-only preflight without execution-frontier or UX polling."""

from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from backend.app.services.runtime_database_incident_gate import (
    evaluate_runtime_database_mutation,
)
from scripts.maintenance.runtime_pressure_gate_core import (
    collect_pgbouncer_metrics,
    collect_runner_capacity,
)
from scripts.maintenance.postgres_signal_observer_core import (
    canonical_observer_artifact_sha256,
)
from .compose_policy import collect_observer_compose_policy
from .permit_binding import (
    OBSERVER_OWNER,
    QUALIFICATION_SCHEMA,
    diagnostic_permit_admission,
)


RunCommand = Callable[[list[str], float], dict[str, Any]]
FetchUrl = Callable[[str, float], dict[str, Any]]


_RUNTIME_CONTAINER_NAMES = (
    "mindscape-ai-local-core-postgres",
    "mindscape-ai-local-core-pgbouncer",
    "mindscape-ai-local-core-backend",
    "mindscape-ai-local-core-backend-control",
    "mindscape-ai-local-core-frontend",
)


@dataclass(frozen=True)
class ObserverPreflightConfig:
    repo_root: Path
    journal_root: Path
    output_json: Path
    artifact_sha256: str
    expected_runner_capacity: int
    owner: str
    phase: str
    timeout_seconds: float = 10.0
    pgbouncer_sample_interval_seconds: float = 5.0

    def validate(self) -> None:
        if self.phase not in {"qualification", "terminal"}:
            raise ValueError("observer_preflight_phase_invalid")
        if len(self.artifact_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.artifact_sha256
        ):
            raise ValueError("observer_preflight_artifact_sha256_invalid")
        if self.expected_runner_capacity <= 0:
            raise ValueError("observer_preflight_runner_capacity_invalid")
        if not self.owner.strip():
            raise ValueError("observer_preflight_owner_missing")
        if self.owner != OBSERVER_OWNER:
            raise ValueError("observer_preflight_owner_invalid")


def run_command(args: list[str], timeout_seconds: float) -> dict[str, Any]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "error_code": "command_timeout",
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
    return {
        "ok": completed.returncode == 0,
        "stdout": completed.stdout,
        "returncode": completed.returncode,
        "error_code": "" if completed.returncode == 0 else "command_failed",
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }


def fetch_url(url: str, timeout_seconds: float) -> dict[str, Any]:
    started = time.monotonic()
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            response.read(1024)
            return {
                "ok": response.status == 200,
                "status": response.status,
                "elapsed_seconds": round(time.monotonic() - started, 3),
            }
    except Exception as exc:
        return {
            "ok": False,
            "status": getattr(exc, "code", None),
            "error_code": type(exc).__name__,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }


def _postgres_scalar(
    command: RunCommand,
    timeout_seconds: float,
    sql: str,
) -> dict[str, Any]:
    result = command(
        [
            "docker",
            "exec",
            "mindscape-ai-local-core-postgres",
            "psql",
            "-XqAt",
            "-U",
            "mindscape",
            "-d",
            "mindscape_core",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            sql,
        ],
        timeout_seconds,
    )
    if not result.get("ok"):
        return {"ok": False, "error_code": "postgres_probe_unavailable"}
    return {"ok": True, "value": str(result.get("stdout") or "").strip()}


def _database_checks(command: RunCommand, timeout_seconds: float) -> dict[str, Any]:
    health = _postgres_scalar(
        command,
        timeout_seconds,
        "SELECT json_build_object("
        "'in_recovery', pg_is_in_recovery(), "
        "'read_only', current_setting('transaction_read_only'), "
        "'lock_waits', (SELECT count(*) FROM pg_stat_activity WHERE wait_event_type='Lock')"
        ")::text;",
    )
    active_install = _postgres_scalar(
        command,
        timeout_seconds,
        "SELECT count(*) FROM capability_install_jobs "
        "WHERE state IN ('queued','running','waiting_db','waiting_db_incident',"
        "'pending_execution_activation');",
    )
    incomplete_commit = _postgres_scalar(
        command,
        timeout_seconds,
        "SELECT count(*) FROM pack_install_commit_receipts "
        "WHERE projection_state <> 'succeeded' "
        "OR filesystem_cleanup_state <> 'succeeded';",
    )
    try:
        metrics = json.loads(health["value"]) if health.get("ok") else {}
        active_count = (
            int(active_install["value"]) if active_install.get("ok") else None
        )
        incomplete_count = (
            int(incomplete_commit["value"]) if incomplete_commit.get("ok") else None
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return {"ok": False, "error_code": "postgres_probe_invalid"}
    return {
        "ok": bool(
            health.get("ok")
            and active_install.get("ok")
            and incomplete_commit.get("ok")
        ),
        "in_recovery": metrics.get("in_recovery"),
        "read_only": metrics.get("read_only"),
        "lock_waits": metrics.get("lock_waits"),
        "active_install_jobs": active_count,
        "incomplete_commit_receipts": incomplete_count,
    }


def _observer_running(command: RunCommand, timeout_seconds: float) -> dict[str, Any]:
    result = command(
        [
            "docker",
            "ps",
            "--filter",
            "name=^mindscape-ai-local-core-postgres-signal-observer$",
            "--format",
            "{{.Names}}",
        ],
        timeout_seconds,
    )
    return {
        "ok": bool(result.get("ok")),
        "running": bool(str(result.get("stdout") or "").strip()),
    }


def _runtime_lifecycle_snapshot(
    command: RunCommand,
    timeout_seconds: float,
) -> dict[str, Any]:
    listed = command(
        [
            "docker",
            "ps",
            "--filter",
            "name=mindscape-ai-local-core-runner",
            "--format",
            "{{.Names}}",
        ],
        timeout_seconds,
    )
    if not listed.get("ok"):
        return {"ok": False, "error_code": "runner_lifecycle_list_unavailable"}
    runner_names = sorted(
        name.strip()
        for name in str(listed.get("stdout") or "").splitlines()
        if name.strip()
    )
    if not runner_names:
        return {"ok": False, "error_code": "runner_lifecycle_empty"}
    container_names = [*_RUNTIME_CONTAINER_NAMES, *runner_names]
    inspected = command(
        [
            "docker",
            "inspect",
            "--format",
            "{{.Name}}|{{.State.StartedAt}}|{{.RestartCount}}|{{.State.Running}}",
            *container_names,
        ],
        timeout_seconds,
    )
    if not inspected.get("ok"):
        return {"ok": False, "error_code": "runtime_lifecycle_inspect_unavailable"}
    rows: list[dict[str, Any]] = []
    try:
        for line in str(inspected.get("stdout") or "").splitlines():
            name, started_at, restart_count, running = line.strip().split("|", 3)
            rows.append(
                {
                    "container": name.removeprefix("/"),
                    "started_at": started_at,
                    "restart_count": int(restart_count),
                    "running": running.lower() == "true",
                }
            )
    except (TypeError, ValueError):
        return {"ok": False, "error_code": "runtime_lifecycle_inspect_invalid"}
    rows.sort(key=lambda row: str(row["container"]))
    if {str(row["container"]) for row in rows} != set(container_names):
        return {"ok": False, "error_code": "runtime_lifecycle_inventory_mismatch"}
    return {
        "ok": all(bool(row["running"]) for row in rows),
        "runner_containers": runner_names,
        "rows": rows,
    }


def _database_state_matches(
    before: dict[str, Any],
    after: dict[str, Any],
) -> bool:
    fields = (
        "in_recovery",
        "read_only",
        "lock_waits",
        "active_install_jobs",
        "incomplete_commit_receipts",
    )
    return bool(
        before.get("ok")
        and after.get("ok")
        and all(before.get(field) == after.get(field) for field in fields)
    )


def _evaluate_failures(
    checks: dict[str, Any], config: ObserverPreflightConfig
) -> list[str]:
    failures: list[str] = []
    if config.phase == "qualification":
        admission = checks["diagnostic_permit_admission"]
        if admission.get("allowed") is not True:
            failures.append(str(admission.get("failure_code") or "state_invalid"))
    if not checks["source_artifact"].get("matches"):
        failures.append("observer_artifact_sha256_mismatch")
    database = checks["database"]
    if not database.get("ok"):
        failures.append("database_checks_unavailable")
    else:
        if database.get("active_install_jobs") != 0:
            failures.append(
                f"active_install_jobs_nonzero:{database.get('active_install_jobs')}"
            )
        if database.get("incomplete_commit_receipts") != 0:
            failures.append(
                "incomplete_commit_receipts_nonzero:"
                f"{database.get('incomplete_commit_receipts')}"
            )
        if database.get("in_recovery") is not False:
            failures.append("postgres_in_recovery")
        if database.get("read_only") != "off":
            failures.append("postgres_read_only")
        if int(database.get("lock_waits") or 0) != 0:
            failures.append(f"postgres_lock_waits_nonzero:{database.get('lock_waits')}")
    lifecycle = checks["runtime_lifecycle"]
    if not lifecycle["before"].get("ok") or not lifecycle["after"].get("ok"):
        failures.append("runtime_lifecycle_unavailable")
    elif not lifecycle.get("stable"):
        failures.append("runtime_lifecycle_changed_during_preflight")
    if not checks.get("database_state_stable"):
        failures.append("database_state_changed_during_preflight")
    pools = checks["pgbouncer"]
    if not pools.get("ok") or pools.get("sample_count") != 3:
        failures.append("pgbouncer_three_samples_unavailable")
    elif any(
        int(row.get("cl_waiting") or 0) != 0 or int(row.get("maxwait") or 0) != 0
        for row in pools.get("rows") or []
    ):
        failures.append("pgbouncer_wait_nonzero")
    runners = checks["runner_capacity"]
    if not runners.get("ok"):
        failures.append("runner_capacity_unavailable")
    elif runners.get("aggregate_max_inflight") != config.expected_runner_capacity:
        failures.append(
            "runner_capacity_changed:"
            f"{runners.get('aggregate_max_inflight')}!={config.expected_runner_capacity}"
        )
    for label, endpoint in checks["endpoints"].items():
        if not endpoint.get("ok") or endpoint.get("status") != 200:
            failures.append(f"endpoint_{label}_unavailable")
    if not checks["compose_policy"].get("ok"):
        failures.append("observer_compose_policy_invalid")
    if not checks["observer_process"].get("ok"):
        failures.append("observer_process_check_unavailable")
    elif checks["observer_process"].get("running"):
        failures.append("observer_already_running")
    if config.phase == "terminal" and (
        not checks["incident_decision"].get("allowed")
        or checks["incident_decision"].get("reason") != "incident_diagnostic_permit"
    ):
        failures.append("incident_diagnostic_permit_missing")
    return failures


def collect_observer_preflight(
    config: ObserverPreflightConfig,
    *,
    command: RunCommand = run_command,
    fetch: FetchUrl = fetch_url,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    config.validate()
    decision = evaluate_runtime_database_mutation(
        "postgres_signal_observer_start",
        evidence={"artifact_sha256": config.artifact_sha256},
        journal_root=config.journal_root,
    )
    admission = (
        diagnostic_permit_admission(config.journal_root)
        if config.phase == "qualification"
        else None
    )
    actual_artifact_sha256 = canonical_observer_artifact_sha256(config.repo_root)
    runtime_lifecycle_before = _runtime_lifecycle_snapshot(
        command, config.timeout_seconds
    )
    database_before = _database_checks(command, config.timeout_seconds)
    pgbouncer = collect_pgbouncer_metrics(
        command,
        config.timeout_seconds,
        sample_count=3,
        sample_interval_seconds=config.pgbouncer_sample_interval_seconds,
        sleep=sleep,
    )
    runner_capacity = collect_runner_capacity(command, config.timeout_seconds)
    endpoints = {
        "execution_8200": fetch(
            "http://127.0.0.1:8200/healthz", config.timeout_seconds
        ),
        "control_8220": fetch("http://127.0.0.1:8220/healthz", config.timeout_seconds),
        "frontend_8300_liveness": fetch(
            "http://127.0.0.1:8300/healthz", config.timeout_seconds
        ),
    }
    compose_policy = collect_observer_compose_policy(command, config)
    observer_process = _observer_running(command, config.timeout_seconds)
    database_after = _database_checks(command, config.timeout_seconds)
    runtime_lifecycle_after = _runtime_lifecycle_snapshot(
        command, config.timeout_seconds
    )
    lifecycle_stable = bool(
        runtime_lifecycle_before.get("ok")
        and runtime_lifecycle_after.get("ok")
        and runtime_lifecycle_before.get("rows") == runtime_lifecycle_after.get("rows")
    )
    checks = {
        "source_artifact": {
            "expected_sha256": config.artifact_sha256,
            "actual_sha256": actual_artifact_sha256,
            "matches": actual_artifact_sha256 == config.artifact_sha256,
        },
        "database": database_after,
        "database_before": database_before,
        "database_state_stable": _database_state_matches(
            database_before, database_after
        ),
        "runtime_lifecycle": {
            "before": runtime_lifecycle_before,
            "after": runtime_lifecycle_after,
            "stable": lifecycle_stable,
        },
        "pgbouncer": pgbouncer,
        "runner_capacity": runner_capacity,
        "endpoints": endpoints,
        "compose_policy": compose_policy,
        "observer_process": observer_process,
        "incident_decision": decision.to_dict(),
    }
    if admission is not None:
        checks["diagnostic_permit_admission"] = admission
    failures = _evaluate_failures(checks, config)
    gate_pass = not failures
    receipt = {
        "scope": "postgres_signal_observer_only",
        "phase": config.phase,
        "gate_pass": gate_pass,
        "first_failure": failures[0] if failures else None,
        "failures": failures,
        "mutation_permit": (
            gate_pass
            and decision.allowed
            and decision.reason == "incident_diagnostic_permit"
        ),
        "quiet_window_owned": False,
        "ownership_scope": "postgres_signal_observer_only",
        "owner": config.owner,
        "artifact_sha256": config.artifact_sha256,
        "incident_id": admission.get("incident_id") if admission else decision.incident_id,
        "execution_frontier_queried": False,
        "parallel_runtime_mutation_detected": not bool(
            lifecycle_stable and checks["database_state_stable"]
        ),
        "queue_runner_pool_capacity_mutation": False,
        "checks": checks,
    }
    if config.phase == "qualification":
        receipt["schema_version"] = QUALIFICATION_SCHEMA
    return receipt
