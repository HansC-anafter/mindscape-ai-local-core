"""Production path for deterministic run harness tool execution."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Optional

from backend.app.models.run_harness import (
    RunHarnessArtifactLineageRef,
    RunHarnessEpisode,
    RunHarnessKind,
    RunHarnessObservation,
    RunHarnessResult,
    RunHarnessSelection,
    RunHarnessStatus,
    ToolAdmissionDecision,
    ToolAdmissionResult,
)
from backend.app.models.run_harness_tool_execution import (
    RunHarnessToolExecutionRequest,
)
from backend.app.services.run_harness.episode_ledger import (
    RunHarnessEpisodeLedgerService,
)
from backend.app.services.run_harness.router import RunHarnessRouter
from backend.app.services.run_harness.tool_admission_policy import (
    ToolAdmissionPolicyEvaluator,
)
from backend.app.services.run_harness.tool_execution_mapping import (
    compact_metadata,
    enum_value,
    escalated_result,
    failure_result,
    first_reason,
    map_execution_result,
    running_duplicate_result,
    selection_escalation_result,
    trace_ref,
    validate_tool_snapshot,
    wait_result,
)
from backend.app.services.unified_tool_executor import (
    ToolExecutionResult,
    UnifiedToolExecutor,
)
from backend.app.services.unified_tool_executor_core.governance_context import (
    VerifiedToolExecutionContext,
)


class RunHarnessToolExecutionService:
    """Execute admitted tools through the run harness ledger boundary."""

    def __init__(
        self,
        *,
        episode_ledger: Optional[RunHarnessEpisodeLedgerService] = None,
        executor: Optional[UnifiedToolExecutor] = None,
        admission_evaluator: Optional[ToolAdmissionPolicyEvaluator] = None,
        router: Optional[RunHarnessRouter] = None,
    ) -> None:
        self.episode_ledger = episode_ledger or RunHarnessEpisodeLedgerService()
        self.executor = executor or UnifiedToolExecutor()
        self.admission_evaluator = (
            admission_evaluator or ToolAdmissionPolicyEvaluator()
        )
        self.router = router or RunHarnessRouter()

    async def execute(
        self,
        request: RunHarnessToolExecutionRequest,
        *,
        external_decision: Any = None,
        governance_context: VerifiedToolExecutionContext | None = None,
    ) -> RunHarnessResult:
        terminal = await self._ledger_call(
            self.episode_ledger.get_terminal_result,
            request.episode_id,
        )
        if terminal is not None:
            return terminal

        observation = await self._ledger_call(
            self.episode_ledger.get_observation,
            request.episode_id,
        )
        if self._has_started_without_terminal(observation):
            return running_duplicate_result(request)

        selection = self.router.select(request.envelope)
        if observation is None:
            await self._create_episode(request, selection)

        if selection.harness_kind != RunHarnessKind.DETERMINISTIC_TOOL:
            return await self._record_terminal_result(
                selection_escalation_result(request, selection),
                event_type="tool_execution_rejected_by_selection",
            )

        await self._append_event(
            request,
            "tool_execution_requested",
            RunHarnessStatus.PENDING,
            metadata={
                "tool_ref": request.tool_ref,
                "side_effect": request.side_effect.value,
                "argument_keys": sorted(str(key) for key in request.arguments.keys()),
                "argument_count": len(request.arguments),
            },
        )

        admission = self.admission_evaluator.evaluate(
            policy=request.policy,
            tool_ref=request.tool_ref,
            side_effect=request.side_effect,
            approval_granted=request.approval_granted,
            rollback_available=request.rollback_available,
        )
        await self._append_admission_event(request, admission)

        if admission.decision == ToolAdmissionDecision.WAIT:
            return await self._record_terminal_result(
                wait_result(request, admission),
                event_type="tool_execution_waiting",
            )
        if admission.decision == ToolAdmissionDecision.DENY:
            return await self._record_terminal_result(
                failure_result(
                    request,
                    "tool_admission_denied",
                    first_reason(admission),
                ),
                event_type="tool_execution_denied",
            )
        if admission.decision == ToolAdmissionDecision.ESCALATE:
            return await self._record_terminal_result(
                escalated_result(
                    request,
                    reason=first_reason(admission),
                ),
                event_type="tool_execution_escalated",
            )

        tool_snapshot = await self._resolve_tool_metadata_snapshot(request.tool_ref)
        if tool_snapshot is None:
            return await self._record_terminal_result(
                failure_result(
                    request,
                    "tool_metadata_snapshot_missing",
                    "Tool metadata snapshot is required before execution.",
                ),
                event_type="tool_execution_failed",
            )

        await self._append_event(
            request,
            "tool_execution_started",
            RunHarnessStatus.RUNNING,
            metadata={
                "tool_ref": request.tool_ref,
                "tool_snapshot": tool_snapshot,
            },
        )

        execution_result = await self._execute_tool(
            request,
            tool_snapshot=tool_snapshot,
            external_decision=external_decision,
            governance_context=governance_context,
        )
        result = map_execution_result(
            request,
            execution_result,
            tool_snapshot,
        )
        completion_event = "tool_execution_failed"
        if result.status == RunHarnessStatus.SUCCEEDED:
            completion_event = "tool_execution_completed"
        elif result.status == RunHarnessStatus.WAITING:
            completion_event = "tool_execution_waiting"
        await self._append_event(
            request,
            completion_event,
            result.status,
            artifact_refs=result.output_artifact_refs,
            metadata={
                "tool_ref": request.tool_ref,
                "success": execution_result.success,
                "error_code": result.failure.code if result.failure else None,
            },
        )
        return await self._record_terminal_result(result)

    async def _create_episode(
        self,
        request: RunHarnessToolExecutionRequest,
        selection: RunHarnessSelection,
    ) -> None:
        episode = RunHarnessEpisode(
            episode_id=request.episode_id,
            intent_envelope_ref=f"run-intent:{request.envelope.decision_id}",
            selection_ref=f"run-selection:{request.episode_id}",
            status=RunHarnessStatus.PENDING,
        )
        selection_snapshot = {
            "run_id": request.run_id,
            "workspace_id": request.envelope.workspace_id,
            "harness_kind": selection.harness_kind.value,
            "profile_id": request.envelope.profile_id,
            "tool_ref": request.tool_ref,
            "selection": selection.model_dump(mode="json"),
            "capability_snapshot_refs": [
                request.envelope.capability_snapshot_ref.model_dump(mode="json")
            ],
        }
        await self._ledger_call(
            self.episode_ledger.create_episode,
            episode,
            selection_snapshot,
        )

    async def _append_admission_event(
        self,
        request: RunHarnessToolExecutionRequest,
        admission: ToolAdmissionResult,
    ) -> None:
        status = RunHarnessStatus.RUNNING
        if admission.decision == ToolAdmissionDecision.WAIT:
            status = RunHarnessStatus.WAITING
        elif admission.decision == ToolAdmissionDecision.DENY:
            status = RunHarnessStatus.FAILED
        elif admission.decision == ToolAdmissionDecision.ESCALATE:
            status = RunHarnessStatus.ESCALATED

        await self._append_event(
            request,
            "tool_admission_evaluated",
            status,
            policy_eval={
                "policy_ref": request.policy.policy_ref,
                "decision": admission.decision.value,
                "reason_codes": admission.reason_codes,
            },
            metadata={
                "tool_ref": request.tool_ref,
                "side_effect": request.side_effect.value,
            },
        )

    async def _append_event(
        self,
        request: RunHarnessToolExecutionRequest,
        event_type: str,
        status: RunHarnessStatus,
        *,
        policy_eval: Optional[dict[str, Any]] = None,
        artifact_refs: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        artifact_lineage = [
            RunHarnessArtifactLineageRef(artifact_ref=artifact_ref).model_dump(
                mode="json"
            )
            for artifact_ref in artifact_refs or []
        ]
        payload = {
            "policy_eval": policy_eval or {},
            "trace_refs": [trace_ref(request).model_dump(mode="json")],
            "artifact_lineage": artifact_lineage,
            "metadata": compact_metadata(metadata or {}),
        }
        await self._ledger_call(
            self.episode_ledger.append_event,
            request.episode_id,
            event_type,
            status.value,
            payload,
        )

    async def _record_terminal_result(
        self,
        result: RunHarnessResult,
        *,
        event_type: Optional[str] = None,
    ) -> RunHarnessResult:
        if event_type is not None:
            await self._append_event_for_result(event_type, result)
        return await self._ledger_call(self.episode_ledger.upsert_result, result)

    async def _append_event_for_result(
        self,
        event_type: str,
        result: RunHarnessResult,
    ) -> None:
        payload = {
            "policy_eval": {},
            "trace_refs": [
                trace.model_dump(mode="json") for trace in result.trace_refs
            ],
            "artifact_lineage": [
                RunHarnessArtifactLineageRef(artifact_ref=artifact_ref).model_dump(
                    mode="json"
                )
                for artifact_ref in result.output_artifact_refs
            ],
            "metadata": compact_metadata(
                {
                    "failure_code": result.failure.code if result.failure else None,
                    "next_action": (
                        result.next_action.disposition.value
                        if result.next_action
                        else None
                    ),
                    "wait_reason": (
                        result.wait_state.reason if result.wait_state else None
                    ),
                }
            ),
        }
        await self._ledger_call(
            self.episode_ledger.append_event,
            result.episode_id,
            event_type,
            result.status.value,
            payload,
        )

    async def _execute_tool(
        self,
        request: RunHarnessToolExecutionRequest,
        *,
        tool_snapshot: dict[str, Any],
        external_decision: Any = None,
        governance_context: VerifiedToolExecutionContext | None = None,
    ) -> ToolExecutionResult:
        try:
            timeout_seconds = float(
                getattr(request.policy, "timeout_seconds", None)
                or tool_snapshot.get("execution_timeout_seconds")
                or 30.0
            )
            governed_arguments = dict(request.arguments)
            snapshot = (
                request.envelope.capability_snapshot_ref
                .execution_admission_snapshot
            )
            if snapshot is not None:
                governed_arguments.update(
                    {
                        "workspace_id": request.envelope.workspace_id,
                        "root_execution_id": request.run_id,
                        "execution_admission_snapshot": snapshot,
                    }
                )
            if request.execution_backend in {"remote", "external_provider"}:
                from backend.app.routes.core.execution_dispatch import (
                    build_external_authorization_context,
                    dispatch_remote_execution,
                )

                remote_result = await dispatch_remote_execution(
                    playbook_code=request.tool_ref,
                    inputs=governed_arguments,
                    workspace_id=request.envelope.workspace_id,
                    profile_id=request.envelope.profile_id,
                    execution_id=request.run_id,
                    trace_id=request.envelope.trace_id,
                    remote_job_type="tool",
                    remote_request_payload={
                        "tool_name": request.tool_ref,
                        "inputs": request.arguments,
                    },
                    external_authorization_context=(
                        build_external_authorization_context(
                            external_decision
                        )
                    ),
                )
                return ToolExecutionResult(
                    success=True,
                    tool_name=request.tool_ref,
                    tool_type="remote",
                    result=remote_result,
                    metadata={"execution_backend": "external_provider"},
                )
            if governance_context is None:
                return await self.executor.execute_tool(
                    request.tool_ref,
                    governed_arguments,
                    timeout=timeout_seconds,
                )
            return await self.executor.execute_tool(
                request.tool_ref,
                governed_arguments,
                timeout=timeout_seconds,
                governance_context=governance_context.for_child(
                    request.tool_ref
                ),
            )
        except Exception as exc:
            return ToolExecutionResult(
                success=False,
                tool_name=request.tool_ref,
                tool_type="unknown",
                error=f"Tool execution failed: {exc}",
            )

    async def _resolve_tool_metadata_snapshot(
        self,
        tool_ref: str,
    ) -> Optional[dict[str, Any]]:
        resolver = getattr(self.executor, "resolve_tool_metadata_snapshot", None)
        if callable(resolver):
            snapshot = await self._maybe_await(resolver(tool_ref))
            return validate_tool_snapshot(snapshot)

        parser = getattr(self.executor, "_parse_tool_name", None)
        getter = getattr(self.executor, "_get_tool", None)
        if not callable(parser) or not callable(getter):
            return None

        tool_type, actual_tool_name = parser(tool_ref)
        tool = await getter(tool_type, actual_tool_name)
        metadata = getattr(tool, "metadata", None) if tool is not None else None
        if metadata is None:
            return None

        snapshot = {
            "tool_name": enum_value(getattr(metadata, "name", None))
            or actual_tool_name,
            "source_type": enum_value(
                getattr(metadata, "source_type", None)
            )
            or tool_type,
            "provider": enum_value(getattr(metadata, "provider", None)),
            "danger_level": enum_value(
                getattr(metadata, "danger_level", None)
            ),
            "version": enum_value(getattr(metadata, "version", None)),
            "execution_timeout_seconds": enum_value(
                getattr(metadata, "execution_timeout_seconds", None)
            ),
        }
        return validate_tool_snapshot(snapshot)

    @staticmethod
    def _has_started_without_terminal(
        observation: Optional[RunHarnessObservation],
    ) -> bool:
        if observation is None:
            return False
        for attempt in observation.episode.attempts:
            for event in attempt.step_events:
                if event.event_type == "tool_execution_started":
                    return True
        return False

    @staticmethod
    async def _ledger_call(func: Any, *args: Any) -> Any:
        return await asyncio.to_thread(func, *args)

    @staticmethod
    async def _maybe_await(value: Any) -> Any:
        if inspect.isawaitable(value):
            return await value
        return value
