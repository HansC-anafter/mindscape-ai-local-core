from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.app.services.runtime_database_incident_gate import (
    IncidentCloseReceipt,
    IncidentContainmentReceipt,
    IncidentDiagnosticPermit,
    IncidentState,
    IncidentTransitionError,
    RuntimeDatabaseIncidentJournal,
    RuntimeDatabaseMutationGate,
    runtime_database_mutation_context,
)


def _close_receipt(
    *,
    soak_window: str = "2026-07-16T00:00:00Z/2026-07-19T00:00:00Z",
) -> IncidentCloseReceipt:
    return IncidentCloseReceipt(
        deep_trigger_classification="postmaster_backend_process_exit",
        deep_trigger_event_sha256="d" * 64,
        fix_commit="0123456789abcdef0123456789abcdef01234567",
        containment_evidence_path="evidence/containment.json",
        containment_evidence_sha256="e" * 64,
        test_evidence_paths=(
            "evidence/source-tests.json",
            "evidence/restore.json",
        ),
        test_evidence_sha256="f" * 64,
        reproduction_evidence_path="evidence/reproduction.json",
        reproduction_evidence_sha256="1" * 64,
        soak_window=soak_window,
        restore_id="restore-001",
        restore_evidence_path="evidence/restore.json",
        restore_evidence_sha256="2" * 64,
        resource_budget_evidence_path="evidence/resource-budget.json",
        resource_budget_evidence_sha256="3" * 64,
        owner="team-leads",
        owner_receipt_path="evidence/owner-receipt.json",
        owner_receipt_sha256="4" * 64,
    )


def _containment_receipt() -> IncidentContainmentReceipt:
    return IncidentContainmentReceipt(
        permit_id="containment-001",
        trigger_classification="unattributed_backend_exit_under_structural_pressure",
        fix_commit="0123456789abcdef0123456789abcdef01234567",
        allowed_operation_keys=(
            "backend_restart",
            "capability_install_job@sha256:" + "a" * 64,
            "capability_migration:ig@sha256:" + "a" * 64,
        ),
        test_evidence_paths=("evidence/source-tests.json", "evidence/restore.json"),
        restore_id="restore-001",
        expires_at="2099-07-17T00:00:00Z",
        owner="team-leads",
    )


def _diagnostic_permit(
    *,
    artifact_sha256: str = "b" * 64,
) -> IncidentDiagnosticPermit:
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    return IncidentDiagnosticPermit(
        permit_id="diagnostic-001",
        source_commit="0123456789abcdef",
        allowed_operation_keys=(
            f"postgres_signal_observer_start@sha256:{artifact_sha256}",
        ),
        test_evidence_paths=("evidence/observer-tests.json",),
        capture_evidence_id="signal-capture-001",
        budget_sha256="c" * 64,
        expires_at=expires_at,
        owner="team-leads",
    )


def _record_live_trigger(
    journal: RuntimeDatabaseIncidentJournal,
    incident_id: str,
    *,
    event_context: str = "live_runtime",
) -> None:
    journal.record_diagnostic_permit(incident_id, _diagnostic_permit())
    journal.record_diagnostic_observation(
        incident_id,
        permit_id="diagnostic-001",
        observation_code="postgres_sigquit_signal_observed",
        evidence={
            "sender_comm": "pg_ctl",
            "sender_host_pid": "100",
            "target_host_pid": "200",
            "target_postgres_pid": "300",
            "application_name": "local-core-backend:core",
            "client_process_pid_available": "true",
            "client_process_pid": "400",
            "event_context": event_context,
            "signal_event_path": "signal-observer/events/event-001.json",
            "signal_event_sha256": "d" * 64,
        },
    )
    journal.revoke_diagnostic_permit(
        incident_id,
        terminal_reason="attribution_event_recorded",
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

    _record_live_trigger(journal, incident.incident_id)
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
                **{
                    **_close_receipt().__dict__,
                    "test_evidence_paths": (),
                }
            ),
        )

    soak_started_at = contained.updated_at
    soak_ended_at = datetime.now(timezone.utc).isoformat()
    closed = journal.close(
        incident.incident_id,
        _close_receipt(soak_window=f"{soak_started_at}/{soak_ended_at}"),
    )
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


def test_open_incident_allows_only_exact_diagnostic_operation(
    tmp_path: Path,
) -> None:
    journal = RuntimeDatabaseIncidentJournal(tmp_path)
    incident = journal.open_incident(failure_code="unexpected_close")
    permit = _diagnostic_permit()
    current = journal.record_diagnostic_permit(incident.incident_id, permit)
    gate = RuntimeDatabaseMutationGate(tmp_path)

    allowed = gate.evaluate(
        "postgres_signal_observer_start",
        {"artifact_sha256": "b" * 64},
    )
    wrong_digest = gate.evaluate(
        "postgres_signal_observer_start",
        {"artifact_sha256": "d" * 64},
    )
    v52 = gate.evaluate(
        "remote_live_practice_v52_diagnostic_retry",
        {"artifact_sha256": "b" * 64},
    )

    assert current.state is IncidentState.OPEN_UNATTRIBUTED
    assert current.diagnostic_permit == permit.to_dict()
    assert allowed.allowed is True
    assert allowed.reason == "incident_diagnostic_permit"
    assert wrong_digest.allowed is False
    assert wrong_digest.reason == "runtime_database_incident_open"
    assert v52.allowed is False
    assert v52.reason == "runtime_database_incident_open"


def test_diagnostic_permit_rejects_non_observer_operation_and_long_duration() -> None:
    permit = _diagnostic_permit()
    with pytest.raises(ValueError, match="operation_key_not_allowed"):
        IncidentDiagnosticPermit(
            **{
                **permit.__dict__,
                "allowed_operation_keys": (
                    "remote_live_practice_v52_diagnostic_retry@sha256:" + "b" * 64,
                ),
            }
        ).validate()

    with pytest.raises(ValueError, match="duration_exceeds_30_minutes"):
        IncidentDiagnosticPermit(
            **{
                **permit.__dict__,
                "expires_at": (
                    datetime.now(timezone.utc) + timedelta(minutes=31)
                ).isoformat(),
            }
        ).validate()


def test_new_failure_revokes_diagnostic_and_containment_permits(
    tmp_path: Path,
) -> None:
    journal = RuntimeDatabaseIncidentJournal(tmp_path)
    incident = journal.open_incident(failure_code="unexpected_close")
    journal.record_diagnostic_permit(incident.incident_id, _diagnostic_permit())

    after_diagnostic_failure = journal.open_incident(
        failure_code="postgres_server_closed_unexpectedly",
        evidence={"source": "test"},
    )
    assert after_diagnostic_failure.state is IncidentState.OPEN_UNATTRIBUTED
    assert after_diagnostic_failure.diagnostic_permit is None

    journal.mark_contained(incident.incident_id, _containment_receipt())
    after_contained_failure = journal.open_incident(
        failure_code="postgres_server_closed_unexpectedly",
        evidence={"source": "test"},
    )
    assert after_contained_failure.state is IncidentState.OPEN_UNATTRIBUTED
    assert after_contained_failure.containment_receipt is None
    assert (
        RuntimeDatabaseMutationGate(tmp_path).evaluate("backend_restart").allowed
        is False
    )

    events_path = next((tmp_path / "incidents").iterdir()) / "events.jsonl"
    event_names = [
        json.loads(line)["event"]
        for line in events_path.read_text(encoding="utf-8").splitlines()
    ]
    assert "diagnostic_permit_revoked_by_failure" in event_names
    assert "containment_revoked_by_failure" in event_names


def test_terminal_diagnostic_permit_consumption_and_ownership_handback_are_distinct(
    tmp_path: Path,
) -> None:
    journal = RuntimeDatabaseIncidentJournal(tmp_path)
    incident = journal.open_incident(failure_code="unexpected_close")
    journal.record_diagnostic_permit(incident.incident_id, _diagnostic_permit())

    consumed = journal.revoke_diagnostic_permit(
        incident.incident_id,
        terminal_reason="formal_drill_sequence_terminal_complete",
    )
    assert consumed.diagnostic_permit is None

    handback = journal.record_diagnostic_ownership_handback(
        incident.incident_id,
        owner="runtime-db-incident-owner",
        terminal_reason="formal_drill_sequence_terminal_complete",
        remaining_resources_verified=True,
    )
    assert handback["owner_before"] == "runtime-db-incident-owner"
    assert handback["owner_after"] == "none"

    events_path = next((tmp_path / "incidents").iterdir()) / "events.jsonl"
    event_names = [
        json.loads(line)["event"]
        for line in events_path.read_text(encoding="utf-8").splitlines()
    ]
    assert event_names[-2:] == [
        "diagnostic_permit_consumed_terminal",
        "diagnostic_observer_ownership_handed_back",
    ]


def test_diagnostic_observation_preserves_exact_active_permit(
    tmp_path: Path,
) -> None:
    journal = RuntimeDatabaseIncidentJournal(tmp_path)
    incident = journal.open_incident(failure_code="unexpected_close")
    permit = _diagnostic_permit()
    journal.record_diagnostic_permit(incident.incident_id, permit)

    observed = journal.record_diagnostic_observation(
        incident.incident_id,
        permit_id=permit.permit_id,
        observation_code="postgres_sigquit_signal_observed",
        evidence={"signal_event_sha256": "a" * 64},
    )

    assert observed.diagnostic_permit == permit.to_dict()
    events_path = next((tmp_path / "incidents").iterdir()) / "events.jsonl"
    last_event = json.loads(events_path.read_text(encoding="utf-8").splitlines()[-1])
    assert last_event["event"] == "diagnostic_observation_recorded"
    assert last_event["permit_id"] == permit.permit_id
    with pytest.raises(IncidentTransitionError, match="does not match"):
        journal.record_diagnostic_observation(
            incident.incident_id,
            permit_id="wrong-permit",
            observation_code="postgres_sigquit_signal_observed",
        )


def test_ownership_handback_rejects_active_permit_or_unverified_resources(
    tmp_path: Path,
) -> None:
    journal = RuntimeDatabaseIncidentJournal(tmp_path)
    incident = journal.open_incident(failure_code="unexpected_close")
    journal.record_diagnostic_permit(incident.incident_id, _diagnostic_permit())

    with pytest.raises(IncidentTransitionError, match="still active"):
        journal.record_diagnostic_ownership_handback(
            incident.incident_id,
            owner="runtime-db-incident-owner",
            terminal_reason="fixture",
            remaining_resources_verified=True,
        )
    with pytest.raises(ValueError, match="resources_not_verified"):
        journal.record_diagnostic_ownership_handback(
            incident.incident_id,
            owner="runtime-db-incident-owner",
            terminal_reason="fixture",
            remaining_resources_verified=False,
        )


def test_close_rejects_unattributed_deep_trigger() -> None:
    with pytest.raises(ValueError, match="requires_attributed"):
        IncidentCloseReceipt(
            **{
                **_close_receipt().__dict__,
                "deep_trigger_classification": "unattributed_backend_exit",
            }
        ).validate()


def test_close_rejects_isolated_drill_as_live_incident_attribution(
    tmp_path: Path,
) -> None:
    journal = RuntimeDatabaseIncidentJournal(tmp_path)
    incident = journal.open_incident(failure_code="unexpected_close")
    _record_live_trigger(
        journal,
        incident.incident_id,
        event_context="isolated_drill",
    )
    contained = journal.mark_contained(
        incident.incident_id,
        _containment_receipt(),
    )

    with pytest.raises(
        IncidentTransitionError,
        match="requires_exact_live_deep_trigger_event",
    ):
        journal.close(
            incident.incident_id,
            _close_receipt(
                soak_window=(
                    f"{contained.updated_at}/"
                    f"{datetime.now(timezone.utc).isoformat()}"
                )
            ),
        )


@pytest.mark.parametrize(
    ("field_name", "value", "failure"),
    [
        (
            "resource_budget_evidence_sha256",
            "",
            "missing required fields",
        ),
        (
            "restore_id",
            "not_required_no_postgres_failure",
            "requires_restore_evidence",
        ),
        (
            "fix_commit",
            "0123456789abcdef",
            "fix_commit_must_be_exact",
        ),
    ],
)
def test_close_requires_machine_bound_p0_evidence(
    field_name: str,
    value: str,
    failure: str,
) -> None:
    with pytest.raises(ValueError, match=failure):
        IncidentCloseReceipt(
            **{
                **_close_receipt().__dict__,
                field_name: value,
            }
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
    assert all(
        json.loads(line)["event"] in {"incident_opened", "failure_observed"}
        for line in events
    )


def test_corrupt_current_receipt_fails_mutation_gate_closed(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "current.json").write_text("not-json", encoding="utf-8")

    decision = RuntimeDatabaseMutationGate(tmp_path).evaluate("index_retirement")

    assert decision.allowed is False
    assert decision.reason == "incident_journal_unavailable"
