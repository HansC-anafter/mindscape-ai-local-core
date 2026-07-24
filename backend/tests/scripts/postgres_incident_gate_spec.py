from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[3] / "scripts/maintenance/postgres_incident_gate.py"


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


def test_cli_pack_install_permit_keeps_incident_open_and_binds_artifact(
    tmp_path: Path,
) -> None:
    opened = _run(tmp_path, "open", "postgres_server_closed_unexpectedly")
    incident_id = json.loads(opened.stdout)["incident_id"]
    artifact_sha256 = "b" * 64

    permitted = _run(
        tmp_path,
        "permit-pack-install",
        incident_id,
        "--permit-id",
        "pack-install-001",
        "--capability-code",
        "yogacoach",
        "--current-version",
        "1.1.34",
        "--candidate-version",
        "1.1.36",
        "--artifact-sha256",
        artifact_sha256,
        "--preflight-evidence-path",
        "evidence/yogacoach-install-preflight.json",
        "--migration-revision",
        "20260711090000",
        "--migration-files-digest",
        "c" * 64,
        "--backout-install-id",
        "install-1.1.34",
        "--backout-artifact-sha256",
        "d" * 64,
        "--expires-at",
        "2099-07-17T00:00:00Z",
        "--owner",
        "workspace-owner",
        "--owner-authorization",
        "direct_install_requested_in_task",
    )
    assert permitted.returncode == 0
    permit_payload = json.loads(permitted.stdout)
    assert permit_payload["state"] == "open_unattributed"
    assert permit_payload["pack_install_permits"][0]["permit_id"] == "pack-install-001"

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
        "a" * 64,
    )

    assert allowed.returncode == 0
    assert json.loads(allowed.stdout)["reason"] == (
        "owner_authorized_pack_install_permit"
    )
    assert blocked.returncode == 2
    assert json.loads(blocked.stdout)["reason"] == "runtime_database_incident_open"


def test_cli_targeted_migration_permit_keeps_incident_open_and_binds_revision(
    tmp_path: Path,
) -> None:
    opened = _run(tmp_path, "open", "postgres_server_closed_unexpectedly")
    incident_id = json.loads(opened.stdout)["incident_id"]
    operation = "alembic_upgrade:alembic.postgres.ini:20260716020000"

    permitted = _run(
        tmp_path,
        "permit-targeted-migration",
        incident_id,
        "--permit-id",
        "pack-ledger-bootstrap-001",
        "--alembic-config-name",
        "alembic.postgres.ini",
        "--revision",
        "20260716020000",
        "--migration-file-sha256",
        "e" * 64,
        "--created-relation",
        "pack_install_commit_receipts",
        "--created-relation",
        "idx_pack_install_commit_receipts_pack_committed",
        "--created-relation",
        "idx_pack_install_commit_receipts_reconcile_due",
        "--preflight-evidence-path",
        "evidence/pack-ledger-bootstrap.json",
        "--expires-at",
        "2099-07-17T00:00:00Z",
        "--owner",
        "workspace-owner",
        "--owner-authorization",
        "direct_install_requested_in_task",
    )

    assert permitted.returncode == 0
    permit_payload = json.loads(permitted.stdout)
    assert permit_payload["state"] == "open_unattributed"
    assert permit_payload["targeted_migration_permits"][0]["revision"] == (
        "20260716020000"
    )

    allowed = _run(tmp_path, "evaluate", operation)
    blocked = _run(
        tmp_path,
        "evaluate",
        "alembic_upgrade:alembic.postgres.ini:20260716020001",
    )
    assert allowed.returncode == 0
    assert json.loads(allowed.stdout)["reason"] == (
        "owner_authorized_targeted_migration_permit"
    )
    assert blocked.returncode == 2
