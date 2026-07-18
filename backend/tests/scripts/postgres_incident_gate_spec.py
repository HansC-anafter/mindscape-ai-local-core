from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "scripts/maintenance/postgres_incident_gate.py"
)


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--journal-root", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def test_cli_exposes_stable_json_and_blocking_exit_code(tmp_path: Path) -> None:
    opened = _run(tmp_path, "open", "postgres_server_closed_unexpectedly")
    assert opened.returncode == 0
    incident_id = json.loads(opened.stdout)["incident_id"]

    evaluated = _run(tmp_path, "evaluate", "pack_install")
    assert evaluated.returncode == 2
    payload = json.loads(evaluated.stdout)
    assert payload["reason"] == "runtime_database_incident_open"
    assert payload["incident_id"] == incident_id


def test_cli_containment_requires_exact_artifact_operation_key(
    tmp_path: Path,
) -> None:
    opened = _run(tmp_path, "open", "postgres_server_closed_unexpectedly")
    incident_id = json.loads(opened.stdout)["incident_id"]
    artifact_sha256 = "a" * 64
    operation_key = f"capability_install_job@sha256:{artifact_sha256}"

    contained = _run(
        tmp_path,
        "contain",
        incident_id,
        "--permit-id",
        "containment-001",
        "--trigger-classification",
        "unattributed_backend_exit_under_structural_pressure",
        "--fix-commit",
        "0123456789abcdef",
        "--allowed-operation-key",
        operation_key,
        "--test-evidence-path",
        "evidence/source-tests.json",
        "--restore-id",
        "restore-preflight-001",
        "--expires-at",
        "2099-07-17T00:00:00Z",
        "--owner",
        "team-leads",
    )
    assert contained.returncode == 0

    allowed = _run(
        tmp_path,
        "evaluate",
        "capability_install_job:job-1",
        "--artifact-sha256",
        artifact_sha256,
    )
    blocked = _run(
        tmp_path,
        "evaluate",
        "capability_install_job:job-2",
        "--artifact-sha256",
        "b" * 64,
    )

    assert allowed.returncode == 0
    assert json.loads(allowed.stdout)["reason"] == "containment_repair_permit"
    assert blocked.returncode == 2
    assert json.loads(blocked.stdout)["reason"] == "runtime_database_incident_contained"


@pytest.mark.parametrize(
    "diagnostic_operation",
    ["postgres_signal_observer_start", "postgres_identity_logging_reload"],
)
def test_cli_records_exact_open_state_diagnostic_permit(
    tmp_path: Path,
    diagnostic_operation: str,
) -> None:
    opened = _run(tmp_path, "open", "postgres_server_closed_unexpectedly")
    incident_id = json.loads(opened.stdout)["incident_id"]
    artifact_sha256 = "b" * 64
    operation_key = f"{diagnostic_operation}@sha256:{artifact_sha256}"
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()

    diagnosed = _run(
        tmp_path,
        "diagnose",
        incident_id,
        "--permit-id",
        "diagnostic-001",
        "--source-commit",
        "0123456789abcdef",
        "--diagnostic-operation",
        diagnostic_operation,
        "--artifact-sha256",
        artifact_sha256,
        "--test-evidence-path",
        "evidence/observer-tests.json",
        "--isolated-drill-id",
        "signal-drill-001",
        "--budget-sha256",
        "c" * 64,
        "--expires-at",
        expires_at,
        "--owner",
        "team-leads",
    )
    allowed = _run(
        tmp_path,
        "evaluate",
        diagnostic_operation,
        "--artifact-sha256",
        artifact_sha256,
    )
    v52 = _run(
        tmp_path,
        "evaluate",
        "remote_live_practice_v52_diagnostic_retry",
        "--artifact-sha256",
        artifact_sha256,
    )

    assert diagnosed.returncode == 0
    diagnosed_payload = json.loads(diagnosed.stdout)
    assert diagnosed_payload["state"] == "open_unattributed"
    assert diagnosed_payload["diagnostic_permit"]["allowed_operation_keys"] == [
        operation_key
    ]
    assert allowed.returncode == 0
    assert json.loads(allowed.stdout)["reason"] == "incident_diagnostic_permit"
    assert v52.returncode == 2
    assert json.loads(v52.stdout)["reason"] == "runtime_database_incident_open"


def test_cli_rejects_caller_owned_diagnostic_operation_key(tmp_path: Path) -> None:
    opened = _run(tmp_path, "open", "postgres_server_closed_unexpectedly")
    incident_id = json.loads(opened.stdout)["incident_id"]
    artifact_sha256 = "d" * 64
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()

    rejected = _run(
        tmp_path,
        "diagnose",
        incident_id,
        "--permit-id",
        "diagnostic-002",
        "--source-commit",
        "0123456789abcdef",
        "--diagnostic-operation",
        "postgres_signal_observer_start",
        "--artifact-sha256",
        artifact_sha256,
        "--allowed-operation-key",
        f"postgres_signal_observer_start@sha256:{artifact_sha256}",
        "--test-evidence-path",
        "evidence/observer-tests.json",
        "--isolated-drill-id",
        "signal-drill-002",
        "--budget-sha256",
        "e" * 64,
        "--expires-at",
        expires_at,
        "--owner",
        "team-leads",
    )

    current = json.loads((tmp_path / "current.json").read_text(encoding="utf-8"))
    assert rejected.returncode == 2
    assert "unrecognized arguments: --allowed-operation-key" in rejected.stderr
    assert current.get("diagnostic_permit") is None


@pytest.mark.parametrize("artifact_sha256", ["", "abc", "g" * 64, "A" * 64])
def test_cli_rejects_invalid_diagnostic_artifact_sha256(
    tmp_path: Path,
    artifact_sha256: str,
) -> None:
    opened = _run(tmp_path, "open", "postgres_server_closed_unexpectedly")
    incident_id = json.loads(opened.stdout)["incident_id"]
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()

    rejected = _run(
        tmp_path,
        "diagnose",
        incident_id,
        "--permit-id",
        "diagnostic-003",
        "--source-commit",
        "0123456789abcdef",
        "--diagnostic-operation",
        "postgres_signal_observer_start",
        "--artifact-sha256",
        artifact_sha256,
        "--test-evidence-path",
        "evidence/observer-tests.json",
        "--isolated-drill-id",
        "signal-drill-003",
        "--budget-sha256",
        "f" * 64,
        "--expires-at",
        expires_at,
        "--owner",
        "team-leads",
    )

    current = json.loads((tmp_path / "current.json").read_text(encoding="utf-8"))
    assert rejected.returncode != 0
    assert "diagnostic_artifact_sha256_invalid" in rejected.stderr
    assert current.get("diagnostic_permit") is None
