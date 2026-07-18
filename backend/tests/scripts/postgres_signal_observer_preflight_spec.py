from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.app.services.runtime_database_incident_gate import (
    IncidentDiagnosticPermit,
    RuntimeDatabaseIncidentJournal,
)
from scripts.maintenance.postgres_signal_observer_preflight_core import (
    ObserverPreflightConfig,
    collect_observer_preflight,
)
from scripts.maintenance.postgres_signal_observer_core import (
    canonical_observer_artifact_sha256,
)


def _compose_payload() -> str:
    return json.dumps(
        {
            "services": {
                "postgres-signal-observer": {
                    "profiles": ["runtime-db-observer"],
                    "read_only": True,
                    "pid": "host",
                    "network_mode": "service:pgbouncer",
                    "cap_add": ["SYS_ADMIN"],
                    "cap_drop": ["ALL"],
                    "cpus": 0.1,
                    "mem_limit": 67_108_864,
                    "pids_limit": 16,
                    "environment": {
                        "PGBOUNCER_ADMIN_URL": "redacted-in-memory-only",
                        "RUNTIME_DATABASE_INCIDENT_DIR": "/data",
                    },
                    "volumes": [
                        {"target": "/app/backend"},
                        {"target": "/app/data"},
                    ],
                }
            }
        }
    )


def _command(*, active_install_jobs: int = 0, lifecycle_changed: bool = False):
    lifecycle_calls = 0

    def run(args: list[str], timeout: float):
        nonlocal lifecycle_calls
        joined = " ".join(args)
        if "docker compose" in joined:
            return {"ok": True, "stdout": _compose_payload()}
        if "SHOW POOLS" in joined:
            return {
                "ok": True,
                "stdout": (
                    "database,cl_active,cl_waiting,sv_active,sv_idle,sv_used,sv_login,maxwait,maxwait_us\n"
                    "mindscape_core,1,0,1,2,0,0,0,0\n"
                    "mindscape_vectors,0,0,0,1,0,0,0,0\n"
                ),
            }
        if "pg_is_in_recovery" in joined:
            return {
                "ok": True,
                "stdout": json.dumps(
                    {"in_recovery": False, "read_only": "off", "lock_waits": 0}
                ),
            }
        if "capability_install_jobs" in joined:
            return {"ok": True, "stdout": str(active_install_jobs)}
        if "pack_install_commit_receipts" in joined:
            return {"ok": True, "stdout": "0"}
        if "name=mindscape-ai-local-core-runner" in joined:
            return {
                "ok": True,
                "stdout": "mindscape-ai-local-core-runner-a\n",
            }
        if ".State.StartedAt" in joined:
            lifecycle_calls += 1
            runner_started_at = (
                "2026-07-17T21:00:30Z"
                if lifecycle_changed and lifecycle_calls > 1
                else "2026-07-17T21:00:00Z"
            )
            rows = [
                "/mindscape-ai-local-core-postgres|2026-07-17T04:03:11Z|0|true",
                "/mindscape-ai-local-core-pgbouncer|2026-07-17T04:03:11Z|0|true",
                "/mindscape-ai-local-core-backend|2026-07-17T04:03:11Z|0|true",
                "/mindscape-ai-local-core-backend-control|2026-07-17T18:05:45Z|0|true",
                "/mindscape-ai-local-core-frontend|2026-07-17T04:03:11Z|0|true",
                "/mindscape-ai-local-core-runner-a|"
                + runner_started_at
                + (
                    "|3|true"
                    if lifecycle_calls > 1 and lifecycle_changed
                    else "|2|true"
                ),
            ]
            return {"ok": True, "stdout": "\n".join(rows) + "\n"}
        if "docker inspect" in joined:
            return {"ok": True, "stdout": "LOCAL_CORE_RUNNER_MAX_INFLIGHT=8\n"}
        if "postgres-signal-observer" in joined and "docker ps" in joined:
            return {"ok": True, "stdout": ""}
        raise AssertionError(args)

    return run


def _fetch(url: str, timeout: float):
    return {"ok": True, "status": 200, "elapsed_seconds": 0.01}


def _config(tmp_path: Path, *, phase: str) -> ObserverPreflightConfig:
    repo_root = Path(__file__).resolve().parents[3]
    return ObserverPreflightConfig(
        repo_root=repo_root,
        journal_root=tmp_path / "journal",
        output_json=tmp_path / "receipt.json",
        artifact_sha256=canonical_observer_artifact_sha256(repo_root),
        expected_runner_capacity=8,
        owner="runtime-db-incident-owner",
        phase=phase,
        pgbouncer_sample_interval_seconds=0,
    )


def test_qualification_passes_without_claiming_mutation_permit(tmp_path: Path) -> None:
    config = _config(tmp_path, phase="qualification")
    RuntimeDatabaseIncidentJournal(config.journal_root).open_incident(
        failure_code="postgres_server_closed_unexpectedly"
    )

    receipt = collect_observer_preflight(
        config,
        command=_command(),
        fetch=_fetch,
        sleep=lambda _: None,
    )

    assert receipt["gate_pass"] is True
    assert receipt["mutation_permit"] is False
    assert receipt["quiet_window_owned"] is False
    assert receipt["execution_frontier_queried"] is False
    assert receipt["parallel_runtime_mutation_detected"] is False
    assert receipt["checks"]["pgbouncer"]["sample_count"] == 3
    assert receipt["checks"]["runtime_lifecycle"]["stable"] is True


def test_liveness_endpoints_are_exact_bounded_and_single_shot(
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, float]] = []

    def fetch(url: str, timeout: float) -> dict[str, object]:
        calls.append((url, timeout))
        return {"ok": True, "status": 200, "elapsed_seconds": 0.01}

    receipt = collect_observer_preflight(
        _config(tmp_path, phase="qualification"),
        command=_command(),
        fetch=fetch,
        sleep=lambda _: None,
    )

    assert calls == [
        ("http://127.0.0.1:8200/healthz", 10.0),
        ("http://127.0.0.1:8220/healthz", 10.0),
        ("http://127.0.0.1:8300/healthz", 10.0),
    ]
    assert set(receipt["checks"]["endpoints"]) == {
        "execution_8200",
        "control_8220",
        "frontend_8300_liveness",
    }
    assert "frontend_8300" not in receipt["checks"]["endpoints"]
    assert ("http://127.0.0.1:8300", 10.0) not in calls


def test_frontend_liveness_failure_uses_exact_label_without_retry(
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, float]] = []

    def fetch(url: str, timeout: float) -> dict[str, object]:
        calls.append((url, timeout))
        if url == "http://127.0.0.1:8300/healthz":
            return {
                "ok": False,
                "status": None,
                "error_code": "TimeoutError",
                "elapsed_seconds": timeout,
            }
        return {"ok": True, "status": 200, "elapsed_seconds": 0.01}

    receipt = collect_observer_preflight(
        _config(tmp_path, phase="qualification"),
        command=_command(),
        fetch=fetch,
        sleep=lambda _: None,
    )

    assert receipt["gate_pass"] is False
    assert receipt["first_failure"] == (
        "endpoint_frontend_8300_liveness_unavailable"
    )
    assert receipt["failures"] == [
        "endpoint_frontend_8300_liveness_unavailable"
    ]
    assert calls.count(("http://127.0.0.1:8300/healthz", 10.0)) == 1
    assert len(calls) == 3
    assert ("http://127.0.0.1:8300", 10.0) not in calls


def test_terminal_requires_exact_diagnostic_permit(tmp_path: Path) -> None:
    config = _config(tmp_path, phase="terminal")
    journal = RuntimeDatabaseIncidentJournal(config.journal_root)
    incident = journal.open_incident(failure_code="postgres_server_closed_unexpectedly")

    blocked = collect_observer_preflight(
        config,
        command=_command(),
        fetch=_fetch,
        sleep=lambda _: None,
    )
    assert blocked["gate_pass"] is False
    assert blocked["first_failure"] == "incident_diagnostic_permit_missing"

    journal.record_diagnostic_permit(
        incident.incident_id,
        IncidentDiagnosticPermit(
            permit_id="diagnostic-001",
            source_commit="0123456789abcdef",
            allowed_operation_keys=(
                "postgres_signal_observer_start@sha256:" + config.artifact_sha256,
            ),
            test_evidence_paths=("evidence/qualification.json",),
            isolated_drill_id="signal-drill-001",
            budget_sha256="b" * 64,
            expires_at=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
            owner="runtime-db-incident-owner",
        ),
    )
    allowed = collect_observer_preflight(
        config,
        command=_command(),
        fetch=_fetch,
        sleep=lambda _: None,
    )

    assert allowed["gate_pass"] is True
    assert allowed["mutation_permit"] is True
    assert allowed["checks"]["incident_decision"]["reason"] == (
        "incident_diagnostic_permit"
    )


def test_active_install_is_first_failure_and_capacity_is_not_changed(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path, phase="qualification")

    receipt = collect_observer_preflight(
        config,
        command=_command(active_install_jobs=1),
        fetch=_fetch,
        sleep=lambda _: None,
    )

    assert receipt["gate_pass"] is False
    assert receipt["first_failure"] == "active_install_jobs_nonzero:1"
    assert receipt["checks"]["runner_capacity"]["aggregate_max_inflight"] == 8
    assert receipt["queue_runner_pool_capacity_mutation"] is False


def test_observer_source_has_no_database_query_or_unbounded_privilege() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    source_paths = [
        repo_root / "scripts/maintenance/postgres_signal_observer_core/service.py",
        repo_root / "scripts/maintenance/postgres_signal_observer_core/pgbouncer.py",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in source_paths)
    compose = (repo_root / "docker/compose/postgres-signal-observer.yml").read_text(
        encoding="utf-8"
    )

    assert "SELECT " not in combined
    assert "trace_pipe" not in combined or "while True" not in combined
    assert "docker.sock" not in compose
    assert "privileged: true" not in compose
    assert "SYS_PTRACE" not in compose
    assert "seccomp=unconfined" not in compose


def test_runner_restart_during_full_window_fails_parallel_mutation_gate(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path, phase="qualification")

    receipt = collect_observer_preflight(
        config,
        command=_command(lifecycle_changed=True),
        fetch=_fetch,
        sleep=lambda _: None,
    )

    assert receipt["gate_pass"] is False
    assert receipt["first_failure"] == "runtime_lifecycle_changed_during_preflight"
    assert receipt["parallel_runtime_mutation_detected"] is True
    before = receipt["checks"]["runtime_lifecycle"]["before"]["rows"][-1]
    after = receipt["checks"]["runtime_lifecycle"]["after"]["rows"][-1]
    assert before["restart_count"] == 2
    assert after["restart_count"] == 3
