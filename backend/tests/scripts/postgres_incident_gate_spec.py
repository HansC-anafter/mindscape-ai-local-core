from __future__ import annotations

import json
import hashlib
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.maintenance.postgres_signal_observer_preflight_core import (
    build_ownership_grant,
    build_ownership_request,
)


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


def _write_json(path: Path, payload: object) -> str:
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path.write_bytes(encoded)
    return hashlib.sha256(encoded).hexdigest()


def _observer_receipt_args(
    tmp_path: Path,
    *,
    incident_id: str,
    artifact_sha256: str,
    expires_at: str,
    owner: str = "runtime-db-incident-owner",
) -> list[str]:
    qualification = {
        "schema_version": "mindscape.postgres-signal-observer-qualification.v2",
        "phase": "qualification",
        "gate_pass": True,
        "first_failure": None,
        "failures": [],
        "scope": "postgres_signal_observer_only",
        "ownership_scope": "postgres_signal_observer_only",
        "owner": owner,
        "mutation_permit": False,
        "quiet_window_owned": False,
        "incident_id": incident_id,
        "artifact_sha256": artifact_sha256,
        "checks": {
            "diagnostic_permit_admission": {
                "schema_version": (
                    "mindscape.postgres-signal-observer-permit-admission.v1"
                ),
                "allowed": True,
                "failure_code": None,
                "incident_id": incident_id,
                "state": "open_unattributed",
                "conflicting_permit": False,
                "payload_persisted": False,
            }
        },
    }
    qualification_path = tmp_path / "qualification.json"
    qualification_sha256 = _write_json(qualification_path, qualification)
    issued_at = datetime.now(timezone.utc).isoformat()
    request = build_ownership_request(
        qualification,
        qualification_receipt_sha256=qualification_sha256,
        exact_operation=(
            "postgres_signal_observer_start@sha256:" + artifact_sha256
        ),
        issued_at=issued_at,
        expires_at=expires_at,
        requested_owner=owner,
    )
    request_path = tmp_path / "ownership-request.json"
    request_sha256 = _write_json(request_path, request)
    grant = build_ownership_grant(
        request,
        ownership_request_receipt_sha256=request_sha256,
        granted_owner=owner,
    )
    grant_path = tmp_path / "ownership-grant.json"
    _write_json(grant_path, grant)
    return [
        "--qualification-receipt",
        str(qualification_path),
        "--ownership-request-receipt",
        str(request_path),
        "--ownership-grant-receipt",
        str(grant_path),
    ]


def _run_observer_diagnose(
    tmp_path: Path,
    *,
    receipt_args: list[str],
    artifact_sha256: str,
    expires_at: str,
    permit_id: str,
) -> subprocess.CompletedProcess[str]:
    return _run(
        tmp_path,
        "diagnose",
        *receipt_args,
        "--permit-id",
        permit_id,
        "--source-commit",
        "0123456789abcdef",
        "--diagnostic-operation",
        "postgres_signal_observer_start",
        "--artifact-sha256",
        artifact_sha256,
        "--test-evidence-path",
        "evidence/observer-tests.json",
        "--capture-evidence-id",
        "signal-capture-bound",
        "--budget-sha256",
        "f" * 64,
        "--expires-at",
        expires_at,
        "--owner",
        "runtime-db-incident-owner",
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
        "0123456789abcdef0123456789abcdef01234567",
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
    owner = (
        "runtime-db-incident-owner"
        if diagnostic_operation == "postgres_signal_observer_start"
        else "team-leads"
    )
    admission_args = (
        _observer_receipt_args(
            tmp_path,
            incident_id=incident_id,
            artifact_sha256=artifact_sha256,
            expires_at=expires_at,
            owner=owner,
        )
        if diagnostic_operation == "postgres_signal_observer_start"
        else ["--incident-id", incident_id]
    )

    diagnosed = _run(
        tmp_path,
        "diagnose",
        *admission_args,
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
        "--capture-evidence-id",
        "signal-capture-001",
        "--budget-sha256",
        "c" * 64,
        "--expires-at",
        expires_at,
        "--owner",
        owner,
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
        "--incident-id",
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
        "--capture-evidence-id",
        "signal-capture-002",
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
        "--incident-id",
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
        "--capture-evidence-id",
        "signal-capture-003",
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


def test_cli_rejects_mismatched_observer_grant_before_permit_write(
    tmp_path: Path,
) -> None:
    opened = _run(tmp_path, "open", "postgres_server_closed_unexpectedly")
    incident_id = json.loads(opened.stdout)["incident_id"]
    artifact_sha256 = "9" * 64
    receipt_args = _observer_receipt_args(
        tmp_path,
        incident_id=incident_id,
        artifact_sha256=artifact_sha256,
        expires_at=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
    )
    grant_path = Path(receipt_args[-1])
    grant = json.loads(grant_path.read_text(encoding="utf-8"))
    grant["incident_id"] = "postgres:forged:incident"
    _write_json(grant_path, grant)

    rejected = _run(
        tmp_path,
        "diagnose",
        *receipt_args,
        "--permit-id",
        "diagnostic-forged",
        "--source-commit",
        "0123456789abcdef",
        "--diagnostic-operation",
        "postgres_signal_observer_start",
        "--artifact-sha256",
        artifact_sha256,
        "--test-evidence-path",
        "evidence/observer-tests.json",
        "--capture-evidence-id",
        "signal-capture-forged",
        "--budget-sha256",
        "f" * 64,
        "--expires-at",
        (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
        "--owner",
        "runtime-db-incident-owner",
    )

    current = json.loads((tmp_path / "current.json").read_text(encoding="utf-8"))
    assert rejected.returncode != 0
    assert "ownership_grant_receipt_invalid" in rejected.stderr
    assert current.get("diagnostic_permit") is None


def test_cli_rejects_caller_incident_id_for_observer_before_permit_write(
    tmp_path: Path,
) -> None:
    opened = _run(tmp_path, "open", "postgres_server_closed_unexpectedly")
    incident_id = json.loads(opened.stdout)["incident_id"]
    artifact_sha256 = "8" * 64

    rejected = _run(
        tmp_path,
        "diagnose",
        "--incident-id",
        incident_id,
        "--permit-id",
        "diagnostic-caller-id",
        "--source-commit",
        "0123456789abcdef",
        "--diagnostic-operation",
        "postgres_signal_observer_start",
        "--artifact-sha256",
        artifact_sha256,
        "--test-evidence-path",
        "evidence/observer-tests.json",
        "--capture-evidence-id",
        "signal-capture-caller-id",
        "--budget-sha256",
        "f" * 64,
        "--expires-at",
        (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
        "--owner",
        "runtime-db-incident-owner",
    )

    current = json.loads((tmp_path / "current.json").read_text(encoding="utf-8"))
    assert rejected.returncode != 0
    assert "observer_incident_id_must_be_receipt_bound" in rejected.stderr
    assert current.get("diagnostic_permit") is None


def test_cli_rejects_mismatched_observer_request_before_permit_write(
    tmp_path: Path,
) -> None:
    opened = _run(tmp_path, "open", "postgres_server_closed_unexpectedly")
    incident_id = json.loads(opened.stdout)["incident_id"]
    artifact_sha256 = "7" * 64
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    receipt_args = _observer_receipt_args(
        tmp_path,
        incident_id=incident_id,
        artifact_sha256=artifact_sha256,
        expires_at=expires_at,
    )
    request_path = Path(receipt_args[3])
    request = json.loads(request_path.read_text(encoding="utf-8"))
    request["incident_id"] = "postgres:forged:request"
    _write_json(request_path, request)

    rejected = _run_observer_diagnose(
        tmp_path,
        receipt_args=receipt_args,
        artifact_sha256=artifact_sha256,
        expires_at=expires_at,
        permit_id="diagnostic-forged-request",
    )

    current = json.loads((tmp_path / "current.json").read_text(encoding="utf-8"))
    assert rejected.returncode != 0
    assert "ownership_request_receipt_invalid" in rejected.stderr
    assert current.get("diagnostic_permit") is None


def test_cli_rejects_observer_permit_expiry_not_bound_to_grant(
    tmp_path: Path,
) -> None:
    opened = _run(tmp_path, "open", "postgres_server_closed_unexpectedly")
    incident_id = json.loads(opened.stdout)["incident_id"]
    artifact_sha256 = "6" * 64
    granted_expiry = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    receipt_args = _observer_receipt_args(
        tmp_path,
        incident_id=incident_id,
        artifact_sha256=artifact_sha256,
        expires_at=granted_expiry,
    )

    rejected = _run_observer_diagnose(
        tmp_path,
        receipt_args=receipt_args,
        artifact_sha256=artifact_sha256,
        expires_at=(datetime.now(timezone.utc) + timedelta(minutes=9)).isoformat(),
        permit_id="diagnostic-expiry-mismatch",
    )

    current = json.loads((tmp_path / "current.json").read_text(encoding="utf-8"))
    assert rejected.returncode != 0
    assert "diagnostic_expires_at_mismatch" in rejected.stderr
    assert current.get("diagnostic_permit") is None


def test_cli_rechecks_receipt_bound_incident_is_still_current(
    tmp_path: Path,
) -> None:
    opened = _run(tmp_path, "open", "postgres_server_closed_unexpectedly")
    incident_id = json.loads(opened.stdout)["incident_id"]
    artifact_sha256 = "5" * 64
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    receipt_args = _observer_receipt_args(
        tmp_path,
        incident_id=incident_id,
        artifact_sha256=artifact_sha256,
        expires_at=expires_at,
    )
    current_path = tmp_path / "current.json"
    current = json.loads(current_path.read_text(encoding="utf-8"))
    current["incident_id"] = incident_id + ":replacement"
    current_path.write_text(json.dumps(current), encoding="utf-8")

    rejected = _run_observer_diagnose(
        tmp_path,
        receipt_args=receipt_args,
        artifact_sha256=artifact_sha256,
        expires_at=expires_at,
        permit_id="diagnostic-stale-incident",
    )

    current = json.loads(current_path.read_text(encoding="utf-8"))
    assert rejected.returncode != 0
    assert "is not current" in rejected.stderr
    assert current.get("diagnostic_permit") is None


def test_cli_revoke_diagnostic_consumes_active_permit(tmp_path: Path) -> None:
    opened = _run(tmp_path, "open", "postgres_server_closed_unexpectedly")
    incident_id = json.loads(opened.stdout)["incident_id"]
    artifact_sha256 = "4" * 64
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    receipt_args = _observer_receipt_args(
        tmp_path,
        incident_id=incident_id,
        artifact_sha256=artifact_sha256,
        expires_at=expires_at,
    )
    diagnosed = _run_observer_diagnose(
        tmp_path,
        receipt_args=receipt_args,
        artifact_sha256=artifact_sha256,
        expires_at=expires_at,
        permit_id="diagnostic-planned-reconfigure",
    )
    assert diagnosed.returncode == 0

    revoked = _run(
        tmp_path,
        "revoke-diagnostic",
        incident_id,
        "--terminal-reason",
        "planned_reconfigure",
    )

    assert revoked.returncode == 0
    assert json.loads(revoked.stdout).get("diagnostic_permit") is None
