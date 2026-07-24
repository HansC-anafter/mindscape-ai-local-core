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


def _close_receipt() -> IncidentCloseReceipt:
    return IncidentCloseReceipt(
        deep_trigger_classification="postmaster_backend_process_exit",
        fix_commit="0123456789abcdef",
        test_evidence_paths=("evidence/classifier.json", "evidence/restore.json"),
        soak_window="2026-07-16T00:00:00Z/2026-07-19T00:00:00Z",
        restore_id="restore-001",
        owner="team-leads",
    )


def _containment_receipt() -> IncidentContainmentReceipt:
    return IncidentContainmentReceipt(
        permit_id="containment-001",
        trigger_classification="unattributed_backend_exit_under_structural_pressure",
        fix_commit="0123456789abcdef",
        allowed_operation_keys=(
            "backend_restart",
            "capability_install_job@sha256:" + "a" * 64,
            "capability_migration:ig@sha256:" + "a" * 64,
        ),
        test_evidence_paths=("evidence/source-tests.json", "evidence/restore.json"),
        restore_id="restore-preflight-001",
        expires_at="2099-07-17T00:00:00Z",
        owner="team-leads",
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


def test_open_deduplicates_and_blocks_mutations(tmp_path: Path) -> None:
    journal = RuntimeDatabaseIncidentJournal(tmp_path)
    first = journal.open_incident(
        failure_code="postgres_server_closed_unexpectedly",
        postmaster_start_time="2026-07-16T10:00:00Z",
        first_failure_at="2026-07-16T10:34:38Z",
    )
    second = journal.open_incident(
        failure_code="postgres_server_closed_unexpectedly",
        postmaster_start_time="2026-07-16T10:00:00Z",
    )

    assert second.incident_id == first.incident_id
    assert second.evidence_count == 2
    decision = RuntimeDatabaseMutationGate(tmp_path).evaluate("pack_install")
    assert decision.allowed is False
    assert decision.reason == "runtime_database_incident_open"
    assert decision.incident_id == first.incident_id


def test_state_machine_requires_containment_and_complete_close_receipt(
    tmp_path: Path,
) -> None:
    journal = RuntimeDatabaseIncidentJournal(tmp_path)
    incident = journal.open_incident(failure_code="unexpected_close")

    with pytest.raises(IncidentTransitionError):
        journal.close(incident.incident_id, _close_receipt())

    contained = journal.mark_contained(
        incident.incident_id,
        _containment_receipt(),
    )
    assert contained.state is IncidentState.CONTAINED_PENDING_SOAK
    assert contained.containment_receipt == _containment_receipt().to_dict()

    blocked = RuntimeDatabaseMutationGate(tmp_path).evaluate("migration")
    assert blocked.allowed is False
    assert blocked.reason == "runtime_database_incident_contained"

    with pytest.raises(ValueError, match="test_evidence_paths"):
        journal.close(
            incident.incident_id,
            IncidentCloseReceipt(
                deep_trigger_classification="known",
                fix_commit="abc",
                test_evidence_paths=(),
                soak_window="window",
                restore_id="restore",
                owner="owner",
            ),
        )

    closed = journal.close(incident.incident_id, _close_receipt())
    assert closed.state is IncidentState.CLOSED
    assert RuntimeDatabaseMutationGate(tmp_path).evaluate("migration").allowed is True


def test_containment_permit_allows_only_exact_operation_and_artifact(
    tmp_path: Path,
) -> None:
    journal = RuntimeDatabaseIncidentJournal(tmp_path)
    incident = journal.open_incident(failure_code="unexpected_close")
    journal.mark_contained(incident.incident_id, _containment_receipt())
    gate = RuntimeDatabaseMutationGate(tmp_path)

    allowed = gate.evaluate(
        "capability_install_job:runtime-job-id",
        {"artifact_sha256": "a" * 64},
    )
    wrong_artifact = gate.evaluate(
        "capability_install_job:runtime-job-id",
        {"artifact_sha256": "b" * 64},
    )
    unlisted = gate.evaluate("index_retirement")

    assert allowed.allowed is True
    assert allowed.reason == "containment_repair_permit"
    assert allowed.details["permit_id"] == "containment-001"
    assert wrong_artifact.allowed is False
    assert wrong_artifact.reason == "runtime_database_incident_contained"
    assert unlisted.allowed is False

    with runtime_database_mutation_context(artifact_sha256="a" * 64):
        nested = gate.evaluate("capability_migration:ig")
    assert nested.allowed is True
    assert nested.details["operation_key"].endswith("a" * 64)


def test_containment_receipt_rejects_wildcards_and_expiry(tmp_path: Path) -> None:
    journal = RuntimeDatabaseIncidentJournal(tmp_path)
    incident = journal.open_incident(failure_code="unexpected_close")
    receipt = _containment_receipt()

    with pytest.raises(ValueError, match="must_be_exact"):
        journal.mark_contained(
            incident.incident_id,
            IncidentContainmentReceipt(
                **{
                    **receipt.__dict__,
                    "allowed_operation_keys": ("capability_install_*",),
                }
            ),
        )
    with pytest.raises(ValueError, match="expired"):
        journal.mark_contained(
            incident.incident_id,
            IncidentContainmentReceipt(
                **{
                    **receipt.__dict__,
                    "expires_at": "2020-01-01T00:00:00Z",
                }
            ),
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


def test_close_rejects_unattributed_deep_trigger() -> None:
    with pytest.raises(ValueError, match="requires_attributed"):
        IncidentCloseReceipt(
            deep_trigger_classification="unattributed_backend_exit",
            fix_commit="abc",
            test_evidence_paths=("evidence.json",),
            soak_window="window",
            restore_id="restore",
            owner="owner",
        ).validate()


def test_cross_caller_concurrency_appends_to_one_incident(tmp_path: Path) -> None:
    journal = RuntimeDatabaseIncidentJournal(tmp_path)

    def observe(index: int) -> str:
        return journal.open_incident(
            failure_code="postgres_server_closed_unexpectedly",
            postmaster_start_time="postmaster-a",
            evidence={"caller": str(index)},
        ).incident_id

    with ThreadPoolExecutor(max_workers=8) as executor:
        incident_ids = list(executor.map(observe, range(24)))

    assert len(set(incident_ids)) == 1
    current = journal.current()
    assert current is not None
    assert current.evidence_count == 24
    digest_dirs = list((tmp_path / "incidents").iterdir())
    assert len(digest_dirs) == 1
    events = (digest_dirs[0] / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(events) == 24
    assert all(json.loads(line)["event"] in {"incident_opened", "failure_observed"} for line in events)


def test_corrupt_current_receipt_fails_mutation_gate_closed(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "current.json").write_text("not-json", encoding="utf-8")

    decision = RuntimeDatabaseMutationGate(tmp_path).evaluate("index_retirement")

    assert decision.allowed is False
    assert decision.reason == "incident_journal_unavailable"
