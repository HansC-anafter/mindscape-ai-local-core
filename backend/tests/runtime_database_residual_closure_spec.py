from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.app.services.runtime_database_incident_gate import (
    ATTRIBUTION_EXHAUSTION_CLASSIFICATION,
    REQUIRED_SEARCHED_SOURCES,
    RESIDUAL_CLOSURE_MODE,
    RESIDUAL_OWNER,
    RESIDUAL_RISK_STATEMENT,
    IncidentAttributionExhaustionReceipt,
    IncidentContainmentReceipt,
    IncidentReceipt,
    IncidentResidualCloseReceipt,
    IncidentState,
    IncidentTransitionError,
    RuntimeDatabaseIncidentJournal,
    RuntimeDatabaseMutationGate,
)


FIX_COMMIT = "0123456789abcdef0123456789abcdef01234567"
RESTORE_ID = "restore-residual-001"
TEST_PATHS = ("evidence/source-tests.json", "evidence/restore.json")


def _exhaustion_receipt(
    incident_id: str,
    *,
    evidence_bundle_sha256: str = "a" * 64,
) -> IncidentAttributionExhaustionReceipt:
    ended_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    started_at = ended_at - timedelta(minutes=5)
    return IncidentAttributionExhaustionReceipt(
        incident_id=incident_id,
        classification=ATTRIBUTION_EXHAUSTION_CLASSIFICATION,
        search_started_at=started_at.isoformat(),
        search_ended_at=ended_at.isoformat(),
        searched_sources=tuple(sorted(REQUIRED_SEARCHED_SOURCES)),
        evidence_bundle_path="evidence/attribution-exhaustion.json",
        evidence_bundle_sha256=evidence_bundle_sha256,
        residual_risk_statement=RESIDUAL_RISK_STATEMENT,
        owner=RESIDUAL_OWNER,
        owner_authorization=(
            "workspace-owner:2026-07-27:"
            "bounded-attribution-convergence-and-close"
        ),
        owner_authorization_path="evidence/owner-authorization.json",
        owner_authorization_sha256="b" * 64,
        search_complete=True,
    )


def _containment_receipt() -> IncidentContainmentReceipt:
    return IncidentContainmentReceipt(
        permit_id="containment-residual-001",
        trigger_classification=ATTRIBUTION_EXHAUSTION_CLASSIFICATION,
        fix_commit=FIX_COMMIT,
        allowed_operation_keys=("backend_restart",),
        test_evidence_paths=TEST_PATHS,
        restore_id=RESTORE_ID,
        expires_at="2099-07-17T00:00:00Z",
        owner=RESIDUAL_OWNER,
    )


def _close_receipt(
    exhaustion_sha256: str,
    *,
    soak_window: str,
) -> IncidentResidualCloseReceipt:
    return IncidentResidualCloseReceipt(
        closure_mode=RESIDUAL_CLOSURE_MODE,
        attribution_exhaustion_sha256=exhaustion_sha256,
        residual_risk_statement=RESIDUAL_RISK_STATEMENT,
        fix_commit=FIX_COMMIT,
        containment_evidence_path="evidence/containment.json",
        containment_evidence_sha256="c" * 64,
        test_evidence_paths=TEST_PATHS,
        test_evidence_sha256="d" * 64,
        reproduction_evidence_path="evidence/non-reproduction.json",
        reproduction_evidence_sha256="e" * 64,
        soak_window=soak_window,
        restore_id=RESTORE_ID,
        restore_evidence_path="evidence/restore.json",
        restore_evidence_sha256="f" * 64,
        resource_budget_evidence_path="evidence/resource-budget.json",
        resource_budget_evidence_sha256="1" * 64,
        owner=RESIDUAL_OWNER,
        owner_receipt_path="evidence/owner-receipt.json",
        owner_receipt_sha256="2" * 64,
    )


def _contained_with_exhaustion(
    journal: RuntimeDatabaseIncidentJournal,
) -> tuple[IncidentReceipt, IncidentAttributionExhaustionReceipt]:
    incident = journal.open_incident(
        failure_code="postgres_server_closed_unexpectedly"
    )
    exhaustion = _exhaustion_receipt(incident.incident_id)
    journal.record_attribution_exhaustion(incident.incident_id, exhaustion)
    contained = journal.mark_contained(
        incident.incident_id,
        _containment_receipt(),
    )
    return contained, exhaustion


def test_residual_close_requires_one_same_journal_exhaustion_receipt(
    tmp_path: Path,
) -> None:
    journal = RuntimeDatabaseIncidentJournal(tmp_path)
    incident = journal.open_incident(
        failure_code="postgres_server_closed_unexpectedly"
    )
    contained = journal.mark_contained(
        incident.incident_id,
        _containment_receipt(),
    )

    with pytest.raises(
        IncidentTransitionError,
        match="requires_exact_attribution_exhaustion_event",
    ):
        journal.close_residual(
            incident.incident_id,
            _close_receipt(
                "a" * 64,
                soak_window=(
                    f"{contained.updated_at}/"
                    f"{datetime.now(timezone.utc).isoformat()}"
                ),
            ),
        )


def test_residual_close_terminal_receipt_is_explicit_and_backward_compatible(
    tmp_path: Path,
) -> None:
    journal = RuntimeDatabaseIncidentJournal(tmp_path)
    contained, exhaustion = _contained_with_exhaustion(journal)
    close_receipt = _close_receipt(
        exhaustion.sha256(),
        soak_window=(
            f"{contained.updated_at}/{datetime.now(timezone.utc).isoformat()}"
        ),
    )

    closed = journal.close_residual(contained.incident_id, close_receipt)

    assert closed.state is IncidentState.CLOSED
    assert closed.close_receipt == close_receipt.to_dict()
    assert closed.containment_receipt is None
    assert RuntimeDatabaseMutationGate(tmp_path).evaluate("backend_restart").allowed
    assert IncidentReceipt.from_dict(closed.to_dict()) == closed


def test_residual_close_uses_current_containment_after_failure_revocation(
    tmp_path: Path,
) -> None:
    journal = RuntimeDatabaseIncidentJournal(tmp_path)
    first_contained, exhaustion = _contained_with_exhaustion(journal)
    reopened = journal.open_incident(
        failure_code="postgres_server_closed_unexpectedly",
    )
    replacement = replace(
        _containment_receipt(),
        permit_id="containment-residual-002",
        trigger_classification="pgbouncer_idle_transaction_timeout",
    )
    current_contained = journal.mark_contained(
        reopened.incident_id,
        replacement,
    )

    closed = journal.close_residual(
        current_contained.incident_id,
        _close_receipt(
            exhaustion.sha256(),
            soak_window=(
                f"{current_contained.updated_at}/"
                f"{datetime.now(timezone.utc).isoformat()}"
            ),
        ),
    )
    event_path = next((tmp_path / "incidents").glob("*/events.jsonl"))
    events = [
        json.loads(line)
        for line in event_path.read_text(encoding="utf-8").splitlines()
    ]

    assert first_contained.incident_id == reopened.incident_id == closed.incident_id
    assert closed.state is IncidentState.CLOSED
    assert sum(event.get("event") == "incident_contained" for event in events) == 2
    assert (
        sum(event.get("event") == "containment_revoked_by_failure" for event in events)
        == 1
    )
    assert events[-1]["event"] == "incident_closed"


def test_residual_close_rejects_exhaustion_hash_mismatch(tmp_path: Path) -> None:
    journal = RuntimeDatabaseIncidentJournal(tmp_path)
    contained, _ = _contained_with_exhaustion(journal)

    with pytest.raises(
        IncidentTransitionError,
        match="attribution_exhaustion_mismatch",
    ):
        journal.close_residual(
            contained.incident_id,
            _close_receipt(
                "9" * 64,
                soak_window=(
                    f"{contained.updated_at}/"
                    f"{datetime.now(timezone.utc).isoformat()}"
                ),
            ),
        )


def test_attribution_exhaustion_is_idempotent_but_not_replaceable(
    tmp_path: Path,
) -> None:
    journal = RuntimeDatabaseIncidentJournal(tmp_path)
    incident = journal.open_incident(
        failure_code="postgres_server_closed_unexpectedly"
    )
    exhaustion = _exhaustion_receipt(incident.incident_id)

    first = journal.record_attribution_exhaustion(
        incident.incident_id,
        exhaustion,
    )
    second = journal.record_attribution_exhaustion(
        incident.incident_id,
        exhaustion,
    )

    assert first == second
    with pytest.raises(
        IncidentTransitionError,
        match="already_recorded",
    ):
        journal.record_attribution_exhaustion(
            incident.incident_id,
            replace(exhaustion, evidence_bundle_sha256="8" * 64),
        )


@pytest.mark.parametrize(
    ("field_name", "value", "failure"),
    [
        ("search_complete", False, "search_incomplete"),
        (
            "classification",
            "healthy_instance_replaced",
            "classification_invalid",
        ),
        (
            "residual_risk_statement",
            "root_cause_known",
            "residual_risk_invalid",
        ),
        ("searched_sources", ("incident_journal",), "sources_incomplete"),
    ],
)
def test_exhaustion_receipt_rejects_health_shortcuts_and_incomplete_search(
    field_name: str,
    value: object,
    failure: str,
) -> None:
    receipt = _exhaustion_receipt("incident-001")

    with pytest.raises(ValueError, match=failure):
        replace(receipt, **{field_name: value}).validate()


def test_new_failure_after_residual_close_opens_a_new_incident(
    tmp_path: Path,
) -> None:
    journal = RuntimeDatabaseIncidentJournal(tmp_path)
    contained, exhaustion = _contained_with_exhaustion(journal)
    closed = journal.close_residual(
        contained.incident_id,
        _close_receipt(
            exhaustion.sha256(),
            soak_window=(
                f"{contained.updated_at}/{datetime.now(timezone.utc).isoformat()}"
            ),
        ),
    )

    next_incident = journal.open_incident(
        failure_code="postgres_server_closed_unexpectedly",
        first_failure_at="2026-07-27T01:02:03Z",
    )

    assert next_incident.incident_id != closed.incident_id
    assert next_incident.state is IncidentState.OPEN_UNATTRIBUTED
