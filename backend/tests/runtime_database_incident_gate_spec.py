from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from backend.app.services.runtime_database_incident_gate import (
    IncidentCloseReceipt,
    IncidentState,
    IncidentTransitionError,
    RuntimeDatabaseIncidentJournal,
    RuntimeDatabaseMutationGate,
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

    contained = journal.mark_contained(incident.incident_id)
    assert contained.state is IncidentState.CONTAINED_PENDING_SOAK

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
