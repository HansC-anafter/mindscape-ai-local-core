"""Production bridge for durable workflow run harness execution."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Optional

from backend.app.models.run_harness import (
    EscalationDisposition,
    RunHarnessEpisode,
    RunHarnessFailure,
    RunHarnessKind,
    RunHarnessNextAction,
    RunHarnessObservation,
    RunHarnessResult,
    RunHarnessSelection,
    RunHarnessStatus,
    RunHarnessTraceRef,
    RunHarnessWaitKind,
    RunHarnessWaitState,
)
from backend.app.models.run_harness_workflow_execution import (
    RunHarnessWorkflowExecutionRequest,
)
from backend.app.services.run_harness.episode_ledger import (
    RunHarnessEpisodeLedgerService,
)
from backend.app.services.run_harness.router import RunHarnessRouter
from backend.app.services.run_harness.workflow_ledger_bridge import (
    RUN_HARNESS_EPISODE_ID_KEY,
    RUN_HARNESS_RUN_ID_KEY,
    RUN_HARNESS_STARTED_RECORDED_KEY,
    RunHarnessWorkflowLedgerBridge,
)

WorkflowStarter = Callable[
    [RunHarnessWorkflowExecutionRequest, dict[str, Any]],
    Awaitable[Any],
]


class RunHarnessWorkflowExecutionService:
    """Start existing workflow runtime executions through the run harness ledger."""

    def __init__(
        self,
        *,
        episode_ledger: Optional[RunHarnessEpisodeLedgerService] = None,
        router: Optional[RunHarnessRouter] = None,
        bridge: Optional[RunHarnessWorkflowLedgerBridge] = None,
        workflow_starter: Optional[WorkflowStarter] = None,
    ) -> None:
        self.episode_ledger = episode_ledger or RunHarnessEpisodeLedgerService()
        self.router = router or RunHarnessRouter()
        self.bridge = bridge or RunHarnessWorkflowLedgerBridge(self.episode_ledger)
        self.workflow_starter = workflow_starter or self._start_via_playbook_service

    async def start(
        self,
        request: RunHarnessWorkflowExecutionRequest,
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
            return self._running_duplicate_result(request)

        selection = self.router.select(request.envelope)
        if observation is None:
            await self._create_episode(request, selection)

        if selection.harness_kind != RunHarnessKind.DURABLE_WORKFLOW:
            return await self._record_terminal_result(
                self._selection_escalation_result(request, selection),
                event_type="workflow_execution_rejected_by_selection",
            )

        await self._append_event(
            request,
            "workflow_execution_requested",
            RunHarnessStatus.PENDING,
            metadata={
                "playbook_code": request.playbook_code,
                "execution_backend": request.execution_backend,
                "input_keys": sorted(
                    str(key) for key in request.normalized_inputs.keys()
                ),
                "input_count": len(request.normalized_inputs),
            },
        )

        normalized_inputs = self._build_runtime_inputs(request)
        self.bridge.record_started(
            request.episode_id,
            request.run_id,
            {
                "playbook_code": request.playbook_code,
                "execution_backend": request.execution_backend,
                "workspace_id": request.workspace_id,
                "project_id": request.project_id,
            },
        )
        normalized_inputs[RUN_HARNESS_STARTED_RECORDED_KEY] = True

        starter_result = await self.workflow_starter(request, normalized_inputs)
        result = self._map_initial_result(request, starter_result)
        return await self._record_terminal_result(result)

    async def _start_via_playbook_service(
        self,
        request: RunHarnessWorkflowExecutionRequest,
        normalized_inputs: dict[str, Any],
    ) -> Any:
        from backend.app.services.playbook_service import PlaybookService

        service = PlaybookService()
        return await service.execute_playbook(
            playbook_code=request.playbook_code,
            workspace_id=request.workspace_id,
            profile_id=request.profile_id,
            inputs=normalized_inputs,
            project_id=request.project_id,
        )

    async def _create_episode(
        self,
        request: RunHarnessWorkflowExecutionRequest,
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
            "workspace_id": request.workspace_id,
            "project_id": request.project_id,
            "profile_id": request.profile_id,
            "harness_kind": selection.harness_kind.value,
            "playbook_code": request.playbook_code,
            "source_execution_id": request.run_id,
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

    async def _append_event(
        self,
        request: RunHarnessWorkflowExecutionRequest,
        event_type: str,
        status: RunHarnessStatus,
        *,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        payload = {
            "policy_eval": {},
            "trace_refs": [self._trace_ref(request).model_dump(mode="json")],
            "artifact_lineage": [],
            "metadata": {
                key: value
                for key, value in (metadata or {}).items()
                if value is not None and not isinstance(value, (bytes, bytearray))
            },
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
            await self._ledger_call(
                self.episode_ledger.append_event,
                result.episode_id,
                event_type,
                result.status.value,
                {
                    "policy_eval": {},
                    "trace_refs": [
                        trace.model_dump(mode="json") for trace in result.trace_refs
                    ],
                    "artifact_lineage": [],
                    "metadata": {
                        "failure_code": (
                            result.failure.code if result.failure else None
                        ),
                        "next_action": (
                            result.next_action.disposition.value
                            if result.next_action
                            else None
                        ),
                    },
                },
            )
        return await self._ledger_call(self.episode_ledger.upsert_result, result)

    def _build_runtime_inputs(
        self,
        request: RunHarnessWorkflowExecutionRequest,
    ) -> dict[str, Any]:
        normalized_inputs = dict(request.normalized_inputs)
        normalized_inputs.setdefault("execution_id", request.run_id)
        normalized_inputs.setdefault("workspace_id", request.workspace_id)
        if request.project_id:
            normalized_inputs.setdefault("project_id", request.project_id)
        normalized_inputs["execution_backend"] = request.execution_backend
        normalized_inputs[RUN_HARNESS_EPISODE_ID_KEY] = request.episode_id
        normalized_inputs[RUN_HARNESS_RUN_ID_KEY] = request.run_id
        return normalized_inputs

    def _map_initial_result(
        self,
        request: RunHarnessWorkflowExecutionRequest,
        starter_result: Any,
    ) -> RunHarnessResult:
        status_text = str(getattr(starter_result, "status", "") or "").lower()
        error = getattr(starter_result, "error", None)
        execution_id = str(getattr(starter_result, "execution_id", "") or request.run_id)
        if status_text in {"error", "failed"}:
            return RunHarnessResult(
                run_id=execution_id,
                episode_id=request.episode_id,
                harness_kind=RunHarnessKind.DURABLE_WORKFLOW,
                status=RunHarnessStatus.FAILED,
                failure=RunHarnessFailure(
                    code="workflow_execution_failed",
                    message=error or "Workflow execution failed.",
                    retryable=False,
                ),
                trace_refs=[self._trace_ref(request)],
                metadata={
                    "ledger_episode_id": request.episode_id,
                    "source_execution_id": execution_id,
                },
            )

        return RunHarnessResult(
            run_id=execution_id,
            episode_id=request.episode_id,
            harness_kind=RunHarnessKind.DURABLE_WORKFLOW,
            status=RunHarnessStatus.WAITING,
            wait_state=RunHarnessWaitState(
                kind=RunHarnessWaitKind.RESOURCE,
                reason="workflow_execution_running",
            ),
            trace_refs=[self._trace_ref(request)],
            metadata={
                "ledger_episode_id": request.episode_id,
                "source_execution_id": execution_id,
                "runtime_status": status_text or "running",
            },
        )

    def _running_duplicate_result(
        self,
        request: RunHarnessWorkflowExecutionRequest,
    ) -> RunHarnessResult:
        return RunHarnessResult(
            run_id=request.run_id,
            episode_id=request.episode_id,
            harness_kind=RunHarnessKind.DURABLE_WORKFLOW,
            status=RunHarnessStatus.WAITING,
            wait_state=RunHarnessWaitState(
                kind=RunHarnessWaitKind.RESOURCE,
                reason="workflow_execution_already_in_progress",
            ),
            trace_refs=[self._trace_ref(request)],
            metadata={"ledger_episode_id": request.episode_id},
        )

    def _selection_escalation_result(
        self,
        request: RunHarnessWorkflowExecutionRequest,
        selection: RunHarnessSelection,
    ) -> RunHarnessResult:
        return RunHarnessResult(
            run_id=request.run_id,
            episode_id=request.episode_id,
            harness_kind=selection.harness_kind,
            status=RunHarnessStatus.ESCALATED,
            next_action=RunHarnessNextAction(
                disposition=EscalationDisposition.QUEUE_MEETING,
                reason="run_harness_selection_not_durable_workflow",
            ),
            trace_refs=[self._trace_ref(request)],
            metadata={
                "ledger_episode_id": request.episode_id,
                "selected_harness_kind": selection.harness_kind.value,
            },
        )

    @staticmethod
    def _has_started_without_terminal(
        observation: Optional[RunHarnessObservation],
    ) -> bool:
        if observation is None:
            return False
        for attempt in observation.episode.attempts:
            for event in attempt.step_events:
                if event.event_type == "workflow_execution_started":
                    return True
        return False

    @staticmethod
    def _trace_ref(
        request: RunHarnessWorkflowExecutionRequest,
    ) -> RunHarnessTraceRef:
        return RunHarnessTraceRef(trace_id=request.envelope.trace_id)

    @staticmethod
    async def _ledger_call(func: Any, *args: Any) -> Any:
        return await asyncio.to_thread(func, *args)
