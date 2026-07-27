from __future__ import annotations

import json

from concurrent.futures import ThreadPoolExecutor

from pathlib import Path

import pytest

from backend.app.services.runtime_database_incident_gate import (
    IncidentCloseReceipt,
    IncidentContainmentReceipt,
    IncidentPackInstallPermitReceipt,
    IncidentState,
    IncidentTargetedMigrationPermitReceipt,
    IncidentTransitionError,
    RuntimeDatabaseIncidentJournal,
    RuntimeDatabaseMutationGate,
    runtime_database_mutation_context,
)

def _pack_install_permit() -> IncidentPackInstallPermitReceipt:
    artifact_sha256 = "b" * 64
    return IncidentPackInstallPermitReceipt(
        permit_id="pack-install-001",
        capability_code="yogacoach",
        current_version="1.1.34",
        candidate_version="1.1.36",
        artifact_sha256=artifact_sha256,
        allowed_operation_keys=(
            f"capability_install_intake:file@sha256:{artifact_sha256}",
            f"capability_install_job@sha256:{artifact_sha256}",
        ),
        preflight_evidence_paths=("evidence/yogacoach-install-preflight.json",),
        migration_revisions=("20260711090000",),
        migration_files_digest="c" * 64,
        schema_mutation_required=False,
        backout_install_id="install-1.1.34",
        backout_artifact_sha256="d" * 64,
        expires_at="2099-07-17T00:00:00Z",
        owner="workspace-owner",
        owner_authorization="direct_install_requested_in_task",
    )

def _targeted_migration_permit() -> IncidentTargetedMigrationPermitReceipt:
    return IncidentTargetedMigrationPermitReceipt(
        permit_id="pack-ledger-bootstrap-001",
        alembic_config_name="alembic.postgres.ini",
        revision="20260716020000",
        migration_file_sha256="e" * 64,
        migration_mode="create_only",
        created_relations=(
            "pack_install_commit_receipts",
            "idx_pack_install_commit_receipts_pack_committed",
            "idx_pack_install_commit_receipts_reconcile_due",
        ),
        allowed_operation_key=(
            "alembic_upgrade:alembic.postgres.ini:20260716020000"
        ),
        preflight_evidence_paths=("evidence/pack-ledger-bootstrap.json",),
        expires_at="2099-07-17T00:00:00Z",
        owner="workspace-owner",
        owner_authorization="direct_install_requested_in_task",
    )

def test_open_incident_allows_only_exact_owner_authorized_pack_install(
    tmp_path: Path,
) -> None:
    journal = RuntimeDatabaseIncidentJournal(tmp_path)
    incident = journal.open_incident(failure_code="unexpected_close")
    permitted = journal.grant_pack_install_permit(
        incident.incident_id,
        _pack_install_permit(),
    )
    gate = RuntimeDatabaseMutationGate(tmp_path)

    assert permitted.state is IncidentState.OPEN_UNATTRIBUTED
    assert len(permitted.pack_install_permits) == 1
    intake = gate.evaluate(
        "capability_install_intake:file",
        {"artifact_sha256": "b" * 64},
    )
    job = gate.evaluate(
        "capability_install_job:runtime-id",
        {"artifact_sha256": "b" * 64},
    )
    wrong_artifact = gate.evaluate(
        "capability_install_job:runtime-id",
        {"artifact_sha256": "a" * 64},
    )
    unrelated = gate.evaluate("backend_restart")

    assert intake.allowed is True
    assert job.allowed is True
    assert intake.reason == "owner_authorized_pack_install_permit"
    assert intake.details["permit_id"] == "pack-install-001"
    assert wrong_artifact.allowed is False
    assert wrong_artifact.reason == "runtime_database_incident_open"
    assert unrelated.allowed is False

def test_pack_install_permit_rejects_schema_mutation_and_wrong_keys() -> None:
    receipt = _pack_install_permit()
    with pytest.raises(ValueError, match="forbids_schema_mutation"):
        IncidentPackInstallPermitReceipt(
            **{**receipt.__dict__, "schema_mutation_required": True}
        ).validate()
    with pytest.raises(ValueError, match="operation_keys_must_be_exact"):
        IncidentPackInstallPermitReceipt(
            **{
                **receipt.__dict__,
                "allowed_operation_keys": (
                    "capability_install_intake:file@sha256:" + "b" * 64,
                ),
            }
        ).validate()

def test_pack_install_permit_accepts_digest_bound_empty_migration_set() -> None:
    receipt = _pack_install_permit()
    IncidentPackInstallPermitReceipt(
        **{
            **receipt.__dict__,
            "migration_revisions": (),
            "migration_files_digest": (
                "e3b0c44298fc1c149afbf4c8996fb924"
                "27ae41e4649b934ca495991b7852b855"
            ),
        }
    ).validate()

    with pytest.raises(
        ValueError,
        match="empty_migration_set_digest_mismatch",
    ):
        IncidentPackInstallPermitReceipt(
            **{
                **receipt.__dict__,
                "migration_revisions": (),
                "migration_files_digest": "c" * 64,
            }
        ).validate()

def test_open_incident_allows_only_exact_owner_authorized_targeted_migration(
    tmp_path: Path,
) -> None:
    journal = RuntimeDatabaseIncidentJournal(tmp_path)
    incident = journal.open_incident(failure_code="unexpected_close")
    permitted = journal.grant_targeted_migration_permit(
        incident.incident_id,
        _targeted_migration_permit(),
    )
    gate = RuntimeDatabaseMutationGate(tmp_path)

    exact = gate.evaluate(
        "alembic_upgrade:alembic.postgres.ini:20260716020000"
    )
    wrong_revision = gate.evaluate(
        "alembic_upgrade:alembic.postgres.ini:20260716020001"
    )
    unrelated = gate.evaluate("backend_restart")

    assert permitted.state is IncidentState.OPEN_UNATTRIBUTED
    assert len(permitted.targeted_migration_permits) == 1
    assert exact.allowed is True
    assert exact.reason == "owner_authorized_targeted_migration_permit"
    assert exact.details["permit_id"] == "pack-ledger-bootstrap-001"
    assert wrong_revision.allowed is False
    assert wrong_revision.reason == "runtime_database_incident_open"
    assert unrelated.allowed is False

def test_targeted_migration_permit_rejects_non_create_and_inexact_operation() -> None:
    receipt = _targeted_migration_permit()
    with pytest.raises(ValueError, match="requires_create_only"):
        IncidentTargetedMigrationPermitReceipt(
            **{**receipt.__dict__, "migration_mode": "alter_existing"}
        ).validate()
    with pytest.raises(ValueError, match="operation_key_must_be_exact"):
        IncidentTargetedMigrationPermitReceipt(
            **{**receipt.__dict__, "allowed_operation_key": "alembic_upgrade:*"}
        ).validate()
