import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.app.services.runtime_database_incident_core.closure_journal import (
    IncidentTransitionError,
)
from backend.app.services.runtime_database_incident_core.journal import (
    RuntimeDatabaseIncidentJournal,
)
from backend.app.services.runtime_database_incident_core.models import (
    IncidentContainmentReceipt,
    IncidentState,
)


def _containment() -> IncidentContainmentReceipt:
    return IncidentContainmentReceipt(
        permit_id="containment-reopen-001",
        trigger_classification="vector-auth-source-drift",
        fix_commit="a177ec19742fde7c46f0373dee99f32383b4d97f",
        allowed_operation_keys=("capability_install_intake:file@sha256:" + "a" * 64,),
        test_evidence_paths=("evidence/preflight.json",),
        restore_id="restore-001",
        expires_at=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
        owner="runtime-db-incident-owner",
    )


def test_reopen_for_attribution_requires_owner_receipt(tmp_path: Path) -> None:
    authorization = tmp_path / "authorization.json"
    authorization.write_text(json.dumps({"authorization": "reopen"}), encoding="utf-8")
    authorization_sha256 = hashlib.sha256(authorization.read_bytes()).hexdigest()
    journal = RuntimeDatabaseIncidentJournal(tmp_path / "journal")
    incident = journal.open_incident(failure_code="postgres_server_closed_unexpectedly")
    journal.mark_contained(incident.incident_id, _containment())

    reopened = journal.reopen_for_attribution(
        incident.incident_id,
        owner="runtime-db-incident-owner",
        authorization="workspace-owner:reopen",
        authorization_path=str(authorization),
        authorization_sha256=authorization_sha256,
        reason="containment_preceded_attribution_exhaustion",
    )

    assert reopened.state is IncidentState.OPEN_UNATTRIBUTED
    assert reopened.containment_receipt is None
    events = journal._read_events_unlocked(incident.incident_id)
    assert events[-1]["event"] == "containment_reopened_for_attribution"


def test_reopen_for_attribution_rejects_invalid_reason(tmp_path: Path) -> None:
    authorization = tmp_path / "authorization.json"
    authorization.write_text("reopen", encoding="utf-8")
    journal = RuntimeDatabaseIncidentJournal(tmp_path / "journal")
    incident = journal.open_incident(failure_code="postgres_server_closed_unexpectedly")
    with pytest.raises(ValueError, match="attribution_reopen_reason_invalid"):
        journal.reopen_for_attribution(
            incident.incident_id,
            owner="runtime-db-incident-owner",
            authorization="workspace-owner:reopen",
            authorization_path=str(authorization),
            authorization_sha256=hashlib.sha256(authorization.read_bytes()).hexdigest(),
            reason="unexpected_reason",
        )


def test_containment_renewal_preserves_scope(tmp_path: Path) -> None:
    journal = RuntimeDatabaseIncidentJournal(tmp_path / "journal")
    incident = journal.open_incident(failure_code="postgres_server_closed_unexpectedly")
    original = _containment()
    journal.mark_contained(incident.incident_id, original)
    renewed = IncidentContainmentReceipt(
        permit_id="containment-reopen-renewed",
        trigger_classification=original.trigger_classification,
        fix_commit=original.fix_commit,
        allowed_operation_keys=original.allowed_operation_keys,
        test_evidence_paths=original.test_evidence_paths,
        restore_id=original.restore_id,
        expires_at=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
        owner=original.owner,
    )

    current = journal.renew_containment(
        incident.incident_id,
        renewed,
        authorization="workspace-owner:renew-containment",
    )

    assert current.containment_receipt == renewed.to_dict()
