from backend.app.models.run_harness import (
    SideEffectClass,
    ToolAdmissionDecision,
    ToolAdmissionPolicy,
)
from backend.app.services.run_harness.tool_admission_policy import (
    ToolAdmissionPolicyEvaluator,
)


def test_write_tool_waits_for_approval() -> None:
    result = ToolAdmissionPolicyEvaluator().evaluate(
        policy=ToolAdmissionPolicy(policy_ref="policy-1"),
        tool_ref="tool-1",
        side_effect=SideEffectClass.EXTERNAL_WRITE,
    )
    assert result.decision == ToolAdmissionDecision.WAIT


def test_readonly_tool_is_admitted() -> None:
    result = ToolAdmissionPolicyEvaluator().evaluate(
        policy=ToolAdmissionPolicy(policy_ref="policy-1"),
        tool_ref="tool-1",
        side_effect=SideEffectClass.READONLY,
    )
    assert result.decision == ToolAdmissionDecision.ALLOW

