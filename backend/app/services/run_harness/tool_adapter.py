"""Admission-gated deterministic tool adapter."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from backend.app.models.run_harness import (
    EscalationDisposition,
    RunHarnessFailure,
    RunHarnessKind,
    RunHarnessNextAction,
    RunHarnessResult,
    RunHarnessStatus,
    SideEffectClass,
    ToolAdmissionDecision,
    ToolAdmissionPolicy,
)
from backend.app.services.run_harness.tool_admission_policy import (
    ToolAdmissionPolicyEvaluator,
)


class DeterministicToolHarnessAdapter:
    def __init__(self, evaluator: ToolAdmissionPolicyEvaluator | None = None) -> None:
        self.evaluator = evaluator or ToolAdmissionPolicyEvaluator()

    async def execute(
        self,
        *,
        run_id: str,
        episode_id: str,
        tool_ref: str,
        arguments: dict[str, Any],
        side_effect: SideEffectClass,
        policy: ToolAdmissionPolicy,
        executor: Callable[[str, dict[str, Any]], Any],
        approval_granted: bool = False,
        rollback_available: bool = False,
    ) -> RunHarnessResult:
        admission = self.evaluator.evaluate(
            policy=policy,
            tool_ref=tool_ref,
            side_effect=side_effect,
            approval_granted=approval_granted,
            rollback_available=rollback_available,
        )
        if admission.decision == ToolAdmissionDecision.WAIT:
            return RunHarnessResult(
                run_id=run_id,
                episode_id=episode_id,
                harness_kind=RunHarnessKind.DETERMINISTIC_TOOL,
                status=RunHarnessStatus.WAITING,
                wait_state=admission.wait_state,
            )
        if admission.decision == ToolAdmissionDecision.ESCALATE:
            return RunHarnessResult(
                run_id=run_id,
                episode_id=episode_id,
                harness_kind=RunHarnessKind.DETERMINISTIC_TOOL,
                status=RunHarnessStatus.ESCALATED,
                next_action=RunHarnessNextAction(
                    disposition=EscalationDisposition.QUEUE_MEETING,
                    reason=admission.reason_codes[0],
                ),
            )
        if admission.decision == ToolAdmissionDecision.DENY:
            return RunHarnessResult(
                run_id=run_id,
                episode_id=episode_id,
                harness_kind=RunHarnessKind.DETERMINISTIC_TOOL,
                status=RunHarnessStatus.FAILED,
                failure=RunHarnessFailure(
                    code="tool_admission_denied",
                    message=admission.reason_codes[0],
                ),
            )
        try:
            output = executor(tool_ref, arguments)
            if inspect.isawaitable(output):
                output = await output
        except Exception as exc:
            return RunHarnessResult(
                run_id=run_id,
                episode_id=episode_id,
                harness_kind=RunHarnessKind.DETERMINISTIC_TOOL,
                status=RunHarnessStatus.FAILED,
                failure=RunHarnessFailure(
                    code="tool_execution_failed",
                    message=str(exc),
                    retryable=False,
                ),
            )
        payload = output if isinstance(output, dict) else {}
        return RunHarnessResult(
            run_id=run_id,
            episode_id=episode_id,
            harness_kind=RunHarnessKind.DETERMINISTIC_TOOL,
            status=RunHarnessStatus.SUCCEEDED,
            output_artifact_refs=[str(item) for item in payload.get("artifact_refs", [])],
            metadata={"tool_ref": tool_ref},
        )

