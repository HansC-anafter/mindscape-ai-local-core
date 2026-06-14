"""Deterministic admission policy for tool adapter calls."""

from backend.app.models.run_harness import (
    RunHarnessWaitKind,
    RunHarnessWaitState,
    SideEffectClass,
    ToolAdmissionDecision,
    ToolAdmissionPolicy,
    ToolAdmissionResult,
)


class ToolAdmissionPolicyEvaluator:
    def evaluate(
        self,
        *,
        policy: ToolAdmissionPolicy,
        tool_ref: str,
        side_effect: SideEffectClass,
        approval_granted: bool = False,
        rollback_available: bool = False,
    ) -> ToolAdmissionResult:
        if tool_ref in policy.denied_tool_refs:
            return ToolAdmissionResult(
                decision=ToolAdmissionDecision.DENY,
                reason_codes=["tool_explicitly_denied"],
            )
        if policy.allowed_tool_refs and tool_ref not in policy.allowed_tool_refs:
            return ToolAdmissionResult(
                decision=ToolAdmissionDecision.DENY,
                reason_codes=["tool_not_in_allowlist"],
            )
        if side_effect not in policy.allowed_side_effects:
            if side_effect in policy.require_approval_for and not approval_granted:
                return ToolAdmissionResult(
                    decision=ToolAdmissionDecision.WAIT,
                    reason_codes=["human_approval_required"],
                    wait_state=RunHarnessWaitState(
                        kind=RunHarnessWaitKind.HUMAN_APPROVAL,
                        reason="Tool side effects require approval.",
                    ),
                )
            return ToolAdmissionResult(
                decision=ToolAdmissionDecision.DENY,
                reason_codes=["side_effect_not_allowed"],
            )
        if side_effect == SideEffectClass.DESTRUCTIVE and not (
            rollback_available or policy.rollback_plan_ref
        ):
            return ToolAdmissionResult(
                decision=ToolAdmissionDecision.ESCALATE,
                reason_codes=["destructive_tool_missing_rollback"],
            )
        return ToolAdmissionResult(
            decision=ToolAdmissionDecision.ALLOW,
            reason_codes=["tool_admitted"],
        )

