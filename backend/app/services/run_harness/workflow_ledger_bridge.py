"""Ledger bridge for durable workflow runtime lifecycle events."""

from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

from backend.app.models.run_harness import (
    RunHarnessArtifactLineageRef,
    RunHarnessFailure,
    RunHarnessKind,
    RunHarnessResult,
    RunHarnessStatus,
    RunHarnessWaitKind,
    RunHarnessWaitState,
)
from backend.app.services.run_harness.episode_ledger import (
    RunHarnessEpisodeLedgerService,
)


RUN_HARNESS_EPISODE_ID_KEY = "run_harness_episode_id"
RUN_HARNESS_RUN_ID_KEY = "run_harness_run_id"
RUN_HARNESS_STARTED_RECORDED_KEY = "_run_harness_started_recorded"
logger = logging.getLogger(__name__)


class RunHarnessWorkflowLedgerBridge:
    """Persist workflow lifecycle state to the shared run harness episode ledger."""

    def __init__(
        self,
        episode_ledger: Optional[RunHarnessEpisodeLedgerService] = None,
    ) -> None:
        self.episode_ledger = episode_ledger or RunHarnessEpisodeLedgerService()

    def record_started(
        self,
        episode_id: str,
        execution_id: str,
        metadata: dict[str, Any],
    ) -> None:
        self._append_event(
            episode_id,
            "workflow_execution_started",
            RunHarnessStatus.RUNNING,
            metadata={
                "execution_id": execution_id,
                **_compact_metadata(metadata),
            },
        )

    def record_pending(
        self,
        episode_id: str,
        execution_id: str,
        checkpoint: Optional[dict[str, Any]],
        error: Optional[str],
    ) -> RunHarnessResult:
        checkpoint_summary = _checkpoint_summary(checkpoint)
        wait_kind = (
            RunHarnessWaitKind.HUMAN_APPROVAL
            if checkpoint_summary.get("pause_mode") == "user_reserved"
            else RunHarnessWaitKind.RESOURCE
        )
        result = RunHarnessResult(
            run_id=execution_id,
            episode_id=episode_id,
            harness_kind=RunHarnessKind.DURABLE_WORKFLOW,
            status=RunHarnessStatus.WAITING,
            wait_state=RunHarnessWaitState(
                kind=wait_kind,
                reason=(
                    "Workflow runtime paused at a resumable checkpoint."
                    if wait_kind == RunHarnessWaitKind.HUMAN_APPROVAL
                    else "workflow_checkpoint_wait"
                ),
                resume_token=checkpoint_summary.get("resume_token"),
            ),
            metadata={
                "ledger_episode_id": episode_id,
                "source_execution_id": execution_id,
                "checkpoint_available": bool(checkpoint_summary),
            },
        )
        self._append_event(
            episode_id,
            "workflow_execution_pending",
            RunHarnessStatus.WAITING,
            metadata={
                "execution_id": execution_id,
                "error": error,
                "checkpoint": checkpoint_summary,
            },
        )
        return self.episode_ledger.upsert_result(result)

    def record_terminal(
        self,
        episode_id: str,
        execution_id: str,
        runtime_result: object,
        compact_result: dict[str, Any],
    ) -> RunHarnessResult:
        failed = _runtime_failed(runtime_result, compact_result)
        status = RunHarnessStatus.FAILED if failed else RunHarnessStatus.SUCCEEDED
        artifact_refs = _extract_artifact_refs(runtime_result, compact_result)
        result = RunHarnessResult(
            run_id=execution_id,
            episode_id=episode_id,
            harness_kind=RunHarnessKind.DURABLE_WORKFLOW,
            status=status,
            output_artifact_refs=artifact_refs,
            failure=(
                RunHarnessFailure(
                    code="workflow_execution_failed",
                    message=_runtime_error_message(runtime_result, compact_result),
                    retryable=bool(getattr(runtime_result, "checkpoint", None)),
                )
                if failed
                else None
            ),
            metadata={
                "ledger_episode_id": episode_id,
                "source_execution_id": execution_id,
                "runtime_status": getattr(runtime_result, "status", None),
                "checkpoint_available": bool(getattr(runtime_result, "checkpoint", None)),
            },
        )
        self._append_event(
            episode_id,
            (
                "workflow_execution_failed"
                if status == RunHarnessStatus.FAILED
                else "workflow_execution_completed"
            ),
            status,
            artifact_refs=artifact_refs,
            metadata={
                "execution_id": execution_id,
                "runtime_status": getattr(runtime_result, "status", None),
                "failure_code": result.failure.code if result.failure else None,
            },
        )
        return self.episode_ledger.upsert_result(result)

    def record_failed(
        self,
        episode_id: str,
        execution_id: str,
        error: Exception | str,
    ) -> RunHarnessResult:
        result = RunHarnessResult(
            run_id=execution_id,
            episode_id=episode_id,
            harness_kind=RunHarnessKind.DURABLE_WORKFLOW,
            status=RunHarnessStatus.FAILED,
            failure=RunHarnessFailure(
                code="workflow_execution_failed",
                message=str(error),
                retryable=False,
            ),
            metadata={
                "ledger_episode_id": episode_id,
                "source_execution_id": execution_id,
            },
        )
        self._append_event(
            episode_id,
            "workflow_execution_failed",
            RunHarnessStatus.FAILED,
            metadata={
                "execution_id": execution_id,
                "failure_code": "workflow_execution_failed",
                "error": str(error),
            },
        )
        return self.episode_ledger.upsert_result(result)

    def _append_event(
        self,
        episode_id: str,
        event_type: str,
        status: RunHarnessStatus,
        *,
        artifact_refs: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        artifact_lineage = [
            RunHarnessArtifactLineageRef(artifact_ref=artifact_ref).model_dump(
                mode="json"
            )
            for artifact_ref in artifact_refs or []
        ]
        self.episode_ledger.append_event(
            episode_id,
            event_type,
            status.value,
            {
                "policy_eval": {},
                "trace_refs": [],
                "artifact_lineage": artifact_lineage,
                "metadata": _compact_metadata(metadata or {}),
            },
        )


def record_run_harness_workflow_started(
    *,
    normalized_inputs: Mapping[str, Any],
    execution_id: str,
    metadata: dict[str, Any],
) -> None:
    if normalized_inputs.get(RUN_HARNESS_STARTED_RECORDED_KEY):
        return
    episode_id = _episode_id_from_inputs(normalized_inputs)
    if episode_id is None:
        return
    try:
        RunHarnessWorkflowLedgerBridge().record_started(
            episode_id,
            execution_id,
            metadata,
        )
    except Exception:
        logger.warning("Failed to record run harness workflow start", exc_info=True)


def record_run_harness_workflow_pending(
    *,
    normalized_inputs: Mapping[str, Any],
    execution_id: str,
    checkpoint: Optional[dict[str, Any]],
    error: Optional[str],
) -> None:
    episode_id = _episode_id_from_inputs(normalized_inputs)
    if episode_id is None:
        return
    try:
        RunHarnessWorkflowLedgerBridge().record_pending(
            episode_id,
            execution_id,
            checkpoint,
            error,
        )
    except Exception:
        logger.warning("Failed to record run harness workflow pending", exc_info=True)


def record_run_harness_workflow_terminal(
    *,
    normalized_inputs: Mapping[str, Any],
    execution_id: str,
    runtime_result: object,
    compact_result: dict[str, Any],
) -> None:
    episode_id = _episode_id_from_inputs(normalized_inputs)
    if episode_id is None:
        return
    try:
        RunHarnessWorkflowLedgerBridge().record_terminal(
            episode_id,
            execution_id,
            runtime_result,
            compact_result,
        )
    except Exception:
        logger.warning("Failed to record run harness workflow terminal", exc_info=True)


def record_run_harness_workflow_failed(
    *,
    normalized_inputs: Mapping[str, Any],
    execution_id: str,
    error: Exception | str,
) -> None:
    episode_id = _episode_id_from_inputs(normalized_inputs)
    if episode_id is None:
        return
    try:
        RunHarnessWorkflowLedgerBridge().record_failed(
            episode_id,
            execution_id,
            error,
        )
    except Exception:
        logger.warning("Failed to record run harness workflow failure", exc_info=True)


def _episode_id_from_inputs(inputs: Mapping[str, Any]) -> Optional[str]:
    episode_id = inputs.get(RUN_HARNESS_EPISODE_ID_KEY)
    if isinstance(episode_id, str) and episode_id.strip():
        return episode_id.strip()
    return None


def _checkpoint_summary(checkpoint: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(checkpoint, dict):
        return {}
    summary: dict[str, Any] = {}
    for key in ("checkpoint_ref", "resume_token", "pause_mode", "step_id", "error_type"):
        value = checkpoint.get(key)
        if isinstance(value, (str, int, float, bool)) and str(value).strip():
            summary[key] = value
    return summary


def _runtime_failed(runtime_result: object, compact_result: Mapping[str, Any]) -> bool:
    if compact_result.get("workflow_failed") is True:
        return True
    status = str(
        getattr(runtime_result, "status", None) or compact_result.get("status") or ""
    ).lower()
    return status in {"failed", "error"}


def _runtime_error_message(
    runtime_result: object,
    compact_result: Mapping[str, Any],
) -> str:
    error = getattr(runtime_result, "error", None) or compact_result.get("error")
    if isinstance(error, str) and error.strip():
        return error
    if compact_result.get("workflow_failed") is True:
        return "Workflow completed with step errors"
    return "Workflow execution failed."


def _extract_artifact_refs(
    runtime_result: object,
    compact_result: Mapping[str, Any],
) -> list[str]:
    candidates = [
        compact_result.get("artifact_refs"),
        compact_result.get("output_artifact_refs"),
    ]
    outputs = getattr(runtime_result, "outputs", None)
    if isinstance(outputs, Mapping):
        candidates.append(outputs.get("artifact_refs"))
    compact_outputs = compact_result.get("outputs")
    if isinstance(compact_outputs, Mapping):
        candidates.append(compact_outputs.get("artifact_refs"))

    for candidate in candidates:
        if isinstance(candidate, list) and all(
            isinstance(item, str) for item in candidate
        ):
            return candidate
    return []


def _compact_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key, value in metadata.items():
        if value is None or isinstance(value, (bytes, bytearray)):
            continue
        if isinstance(value, (str, int, float, bool)):
            compact[key] = value
        elif isinstance(value, Mapping):
            compact[key] = {
                str(inner_key): inner_value
                for inner_key, inner_value in value.items()
                if isinstance(inner_value, (str, int, float, bool))
            }
        elif isinstance(value, list):
            compact[key] = [
                item for item in value if isinstance(item, (str, int, float, bool))
            ]
        else:
            compact[key] = str(value)
    return compact
