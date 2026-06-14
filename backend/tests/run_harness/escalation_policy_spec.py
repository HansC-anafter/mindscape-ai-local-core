from backend.app.models.run_harness import (
    EscalationDisposition,
    EscalationTrigger,
    RunHarnessWaitKind,
)
from backend.app.services.run_harness.escalation_policy import EscalationPolicy


def test_approval_trigger_does_not_queue_meeting() -> None:
    decision = EscalationPolicy().decide(
        EscalationTrigger.HUMAN_APPROVAL_REQUIRED
    )
    assert decision.disposition == EscalationDisposition.REQUEST_APPROVAL
    assert decision.wait_state.kind == RunHarnessWaitKind.HUMAN_APPROVAL


def test_cross_pack_conflict_queues_meeting() -> None:
    decision = EscalationPolicy().decide(EscalationTrigger.CROSS_PACK_CONFLICT)
    assert decision.disposition == EscalationDisposition.QUEUE_MEETING

