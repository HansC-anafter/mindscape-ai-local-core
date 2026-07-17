"""Strict observer-only preflight without execution-frontier or UX polling."""

from __future__ import annotations

import hashlib
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


RunCommand = Callable[[list[str], float], dict[str, Any]]
FetchUrl = Callable[[str, float], dict[str, Any]]


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


def _compose_policy(
    command: RunCommand,
    config: ObserverPreflightConfig,
) -> dict[str, Any]:
    result = command(
        [
            "docker",
            "compose",
            "--project-directory",
            str(config.repo_root),
            "--profile",
            "runtime-db-observer",
            "config",
            "--format",
            "json",
        ],
        config.timeout_seconds,
    )
    if not result.get("ok"):
        return {"ok": False, "error_code": "observer_compose_config_unavailable"}
    try:
        service = json.loads(result.get("stdout") or "{}")["services"][
            "postgres-signal-observer"
        ]
        environment = service.get("environment") or {}
        volume_targets = sorted(
            str(volume.get("target") or "")
            for volume in service.get("volumes") or []
            if isinstance(volume, dict)
        )
        policy = {
            "profiles": service.get("profiles"),
            "read_only": service.get("read_only"),
            "privileged": bool(service.get("privileged", False)),
            "pid": service.get("pid"),
            "network_mode": service.get("network_mode"),
            "cap_add": service.get("cap_add"),
            "cap_drop": service.get("cap_drop"),
            "cpus": float(service.get("cpus") or 0),
            "mem_limit": int(service.get("mem_limit") or 0),
            "pids_limit": int(service.get("pids_limit") or 0),
            "volume_targets": volume_targets,
            "environment_keys": sorted(environment),
        }
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return {"ok": False, "error_code": "observer_compose_config_invalid"}
    policy_sha256 = hashlib.sha256(
        json.dumps(policy, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    expected = {
        "profiles": ["runtime-db-observer"],
        "read_only": True,
        "privileged": False,
        "pid": "host",
        "network_mode": "service:pgbouncer",
        "cap_add": ["SYS_ADMIN"],
        "cap_drop": ["ALL"],
        "cpus": 0.1,
        "mem_limit": 67_108_864,
        "pids_limit": 16,
    }
    policy_matches = all(policy.get(key) == value for key, value in expected.items())
    docker_socket_present = any("docker.sock" in target for target in volume_targets)
    return {
        "ok": policy_matches and not docker_socket_present,
        "policy_sha256": policy_sha256,
        "policy_matches": policy_matches,
        "docker_socket_present": docker_socket_present,
        "resource_budget": {
            "cpus": policy["cpus"],
            "mem_limit": policy["mem_limit"],
            "pids_limit": policy["pids_limit"],
        },
        "cap_add": policy["cap_add"],
        "cap_drop": policy["cap_drop"],
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


def _evaluate_failures(
    checks: dict[str, Any], config: ObserverPreflightConfig
) -> list[str]:
    failures: list[str] = []
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
    actual_artifact_sha256 = canonical_observer_artifact_sha256(config.repo_root)
    checks = {
        "source_artifact": {
            "expected_sha256": config.artifact_sha256,
            "actual_sha256": actual_artifact_sha256,
            "matches": actual_artifact_sha256 == config.artifact_sha256,
        },
        "database": _database_checks(command, config.timeout_seconds),
        "pgbouncer": collect_pgbouncer_metrics(
            command,
            config.timeout_seconds,
            sample_count=3,
            sample_interval_seconds=config.pgbouncer_sample_interval_seconds,
            sleep=sleep,
        ),
        "runner_capacity": collect_runner_capacity(command, config.timeout_seconds),
        "endpoints": {
            "execution_8200": fetch(
                "http://127.0.0.1:8200/healthz", config.timeout_seconds
            ),
            "control_8220": fetch(
                "http://127.0.0.1:8220/healthz", config.timeout_seconds
            ),
            "frontend_8300": fetch("http://127.0.0.1:8300", config.timeout_seconds),
        },
        "compose_policy": _compose_policy(command, config),
        "observer_process": _observer_running(command, config.timeout_seconds),
        "incident_decision": decision.to_dict(),
    }
    failures = _evaluate_failures(checks, config)
    gate_pass = not failures
    return {
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
        "execution_frontier_queried": False,
        "queue_runner_pool_capacity_mutation": False,
        "checks": checks,
    }
