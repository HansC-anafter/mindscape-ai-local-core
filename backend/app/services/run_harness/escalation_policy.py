"""Deterministic escalation disposition policy."""

from backend.app.models.run_harness import (
    EscalationDecision,
    EscalationDisposition,
    EscalationTrigger,
    RunHarnessWaitKind,
    RunHarnessWaitState,
)


class EscalationPolicy:
    def decide(self, trigger: EscalationTrigger) -> EscalationDecision:
        if trigger == EscalationTrigger.HUMAN_APPROVAL_REQUIRED:
            return EscalationDecision(
                trigger=trigger,
                disposition=EscalationDisposition.REQUEST_APPROVAL,
                reason_codes=["approval_gate_required"],
                wait_state=RunHarnessWaitState(
                    kind=RunHarnessWaitKind.HUMAN_APPROVAL,
                    reason="Execution requires explicit human approval.",
                ),
            )
        if trigger == EscalationTrigger.RESOURCE_ADMISSION_DENIED:
            return EscalationDecision(
                trigger=trigger,
                disposition=EscalationDisposition.RETRY_WITH_LOWER_CAPABILITY,
                reason_codes=["resource_budget_denied"],
                wait_state=RunHarnessWaitState(
                    kind=RunHarnessWaitKind.RESOURCE,
                    reason="Required runtime resources are not currently admitted.",
                ),
            )
        if trigger == EscalationTrigger.MISSING_TOOL:
            return EscalationDecision(
                trigger=trigger,
                disposition=EscalationDisposition.REQUEST_STRUCTURED_INPUT,
                reason_codes=["tool_contract_missing"],
                wait_state=RunHarnessWaitState(
                    kind=RunHarnessWaitKind.CAPABILITY,
                    reason="A required tool contract is unavailable.",
                ),
            )
        if trigger == EscalationTrigger.WORKFLOW_STUCK:
            return EscalationDecision(
                trigger=trigger,
                disposition=EscalationDisposition.DETERMINISTIC_REPAIR,
                reason_codes=["workflow_progress_stalled"],
            )
        if trigger == EscalationTrigger.MODEL_UNAVAILABLE_FOR_REQUIRED_REASONING:
            return EscalationDecision(
                trigger=trigger,
                disposition=EscalationDisposition.QUEUE_MEETING,
                reason_codes=["required_reasoning_unavailable"],
                wait_state=RunHarnessWaitState(
                    kind=RunHarnessWaitKind.MODEL,
                    reason="Required reasoning capability is unavailable.",
                ),
            )
        if trigger in {
            EscalationTrigger.POLICY_RISK,
            EscalationTrigger.LOW_CONFIDENCE,
            EscalationTrigger.CROSS_PACK_CONFLICT,
        }:
            return EscalationDecision(
                trigger=trigger,
                disposition=EscalationDisposition.QUEUE_MEETING,
                reason_codes=[f"{trigger.value}_requires_deliberation"],
            )
        return EscalationDecision(
            trigger=trigger,
            disposition=EscalationDisposition.FAIL_CLOSED,
            reason_codes=["unsupported_escalation_trigger"],
        )

