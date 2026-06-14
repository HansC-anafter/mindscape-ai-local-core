"""Build queue-only meeting handoff payloads from escalation decisions."""

from backend.app.models.meeting_command import MeetingCommandEnvelope
from backend.app.models.run_harness import (
    EscalationDecision,
    EscalationDisposition,
    RunIntentEnvelope,
)


class MeetingEscalationAdapter:
    def build_queued_envelope(
        self,
        *,
        intent: RunIntentEnvelope,
        decision: EscalationDecision,
        meeting_id: str,
        thread_id: str | None = None,
    ) -> MeetingCommandEnvelope:
        if decision.disposition != EscalationDisposition.QUEUE_MEETING:
            raise ValueError("meeting handoff requires queue_meeting disposition")
        return MeetingCommandEnvelope(
            workspace_id=intent.workspace_id,
            meeting_id=meeting_id,
            origin_surface="run_harness_escalation",
            actor="system",
            intent_text=intent.intent_text,
            thread_id=thread_id,
            metadata={
                "queue_only": True,
                "decision_id": intent.decision_id,
                "trace_id": intent.trace_id,
                "escalation_trigger": decision.trigger.value,
                "escalation_reason_codes": decision.reason_codes,
            },
        )

