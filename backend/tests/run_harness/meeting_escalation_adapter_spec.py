import pytest

from backend.app.models.run_harness import (
    EscalationDecision,
    EscalationDisposition,
    EscalationTrigger,
)
from backend.app.services.run_harness.meeting_escalation_adapter import (
    MeetingEscalationAdapter,
)


def test_adapter_only_builds_queue_payload(run_intent) -> None:
    envelope = MeetingEscalationAdapter().build_queued_envelope(
        intent=run_intent,
        decision=EscalationDecision(
            trigger=EscalationTrigger.LOW_CONFIDENCE,
            disposition=EscalationDisposition.QUEUE_MEETING,
            reason_codes=["low_confidence_requires_deliberation"],
        ),
        meeting_id="meeting-1",
    )
    assert envelope.metadata["queue_only"] is True
    assert envelope.actor == "system"


def test_adapter_rejects_non_meeting_disposition(run_intent) -> None:
    with pytest.raises(ValueError):
        MeetingEscalationAdapter().build_queued_envelope(
            intent=run_intent,
            decision=EscalationDecision(
                trigger=EscalationTrigger.HUMAN_APPROVAL_REQUIRED,
                disposition=EscalationDisposition.REQUEST_APPROVAL,
                reason_codes=["approval"],
            ),
            meeting_id="meeting-1",
        )

