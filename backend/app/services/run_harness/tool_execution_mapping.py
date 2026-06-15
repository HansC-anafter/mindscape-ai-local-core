"""Mapping helpers for deterministic run harness tool execution."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from backend.app.models.run_harness import (
    EscalationDisposition,
    RunHarnessFailure,
    RunHarnessKind,
    RunHarnessNextAction,
    RunHarnessResult,
    RunHarnessSelection,
    RunHarnessStatus,
    RunHarnessTraceRef,
    RunHarnessWaitKind,
    RunHarnessWaitState,
    ToolAdmissionResult,
)
from backend.app.models.run_harness_tool_execution import (
    RunHarnessToolExecutionRequest,
)
from backend.app.services.unified_tool_executor import ToolExecutionResult


TOOL_METADATA_KEYS = (
    "tool_name",
    "source_type",
    "provider",
    "danger_level",
    "version",
)


def map_execution_result(
    request: RunHarnessToolExecutionRequest,
    execution_result: ToolExecutionResult,
    tool_snapshot: Mapping[str, Any],
) -> RunHarnessResult:
    artifact_refs = extract_artifact_refs(execution_result)
    metadata = {
        "tool_name": execution_result.tool_name,
        "tool_type": execution_result.tool_type,
        "execution_time": execution_result.execution_time,
        "tool_source": (
            execution_result.metadata.get("tool_source")
            or tool_snapshot.get("source_type")
        ),
        "ledger_episode_id": request.episode_id,
    }
    if execution_result.success:
        return RunHarnessResult(
            run_id=request.run_id,
            episode_id=request.episode_id,
            harness_kind=RunHarnessKind.DETERMINISTIC_TOOL,
            status=RunHarnessStatus.SUCCEEDED,
            output_artifact_refs=artifact_refs,
            trace_refs=[trace_ref(request)],
            metadata=metadata,
        )

    return RunHarnessResult(
        run_id=request.run_id,
        episode_id=request.episode_id,
        harness_kind=RunHarnessKind.DETERMINISTIC_TOOL,
        status=RunHarnessStatus.FAILED,
        failure=RunHarnessFailure(
            code="tool_execution_failed",
            message=execution_result.error or "Tool execution failed.",
            retryable=False,
        ),
        output_artifact_refs=artifact_refs,
        trace_refs=[trace_ref(request)],
        metadata=metadata,
    )


def wait_result(
    request: RunHarnessToolExecutionRequest,
    admission: ToolAdmissionResult,
) -> RunHarnessResult:
    return RunHarnessResult(
        run_id=request.run_id,
        episode_id=request.episode_id,
        harness_kind=RunHarnessKind.DETERMINISTIC_TOOL,
        status=RunHarnessStatus.WAITING,
        wait_state=admission.wait_state
        or RunHarnessWaitState(
            kind=RunHarnessWaitKind.HUMAN_APPROVAL,
            reason=first_reason(admission),
        ),
        trace_refs=[trace_ref(request)],
        metadata={"ledger_episode_id": request.episode_id},
    )


def failure_result(
    request: RunHarnessToolExecutionRequest,
    code: str,
    message: str,
) -> RunHarnessResult:
    return RunHarnessResult(
        run_id=request.run_id,
        episode_id=request.episode_id,
        harness_kind=RunHarnessKind.DETERMINISTIC_TOOL,
        status=RunHarnessStatus.FAILED,
        failure=RunHarnessFailure(
            code=code,
            message=message,
            retryable=False,
        ),
        trace_refs=[trace_ref(request)],
        metadata={"ledger_episode_id": request.episode_id},
    )


def escalated_result(
    request: RunHarnessToolExecutionRequest,
    *,
    reason: str,
) -> RunHarnessResult:
    return RunHarnessResult(
        run_id=request.run_id,
        episode_id=request.episode_id,
        harness_kind=RunHarnessKind.DETERMINISTIC_TOOL,
        status=RunHarnessStatus.ESCALATED,
        next_action=RunHarnessNextAction(
            disposition=EscalationDisposition.QUEUE_MEETING,
            reason=reason,
        ),
        trace_refs=[trace_ref(request)],
        metadata={"ledger_episode_id": request.episode_id},
    )


def selection_escalation_result(
    request: RunHarnessToolExecutionRequest,
    selection: RunHarnessSelection,
) -> RunHarnessResult:
    return RunHarnessResult(
        run_id=request.run_id,
        episode_id=request.episode_id,
        harness_kind=selection.harness_kind,
        status=RunHarnessStatus.ESCALATED,
        next_action=RunHarnessNextAction(
            disposition=EscalationDisposition.QUEUE_MEETING,
            reason="run_harness_selection_not_deterministic_tool",
        ),
        trace_refs=[trace_ref(request)],
        metadata={
            "ledger_episode_id": request.episode_id,
            "selected_harness_kind": selection.harness_kind.value,
        },
    )


def running_duplicate_result(
    request: RunHarnessToolExecutionRequest,
) -> RunHarnessResult:
    return RunHarnessResult(
        run_id=request.run_id,
        episode_id=request.episode_id,
        harness_kind=RunHarnessKind.DETERMINISTIC_TOOL,
        status=RunHarnessStatus.WAITING,
        wait_state=RunHarnessWaitState(
            kind=RunHarnessWaitKind.RESOURCE,
            reason="tool_execution_already_in_progress",
        ),
        trace_refs=[trace_ref(request)],
        metadata={"ledger_episode_id": request.episode_id},
    )


def extract_artifact_refs(result: ToolExecutionResult) -> list[str]:
    candidates: list[Any] = []
    if isinstance(result.result, Mapping):
        candidates.append(result.result.get("artifact_refs"))
    if isinstance(result.metadata, Mapping):
        candidates.append(result.metadata.get("artifact_refs"))
    for candidate in candidates:
        if isinstance(candidate, list) and all(
            isinstance(item, str) for item in candidate
        ):
            return candidate
    return []


def validate_tool_snapshot(snapshot: Any) -> Optional[dict[str, Any]]:
    if not isinstance(snapshot, Mapping):
        return None
    if any(key not in snapshot for key in TOOL_METADATA_KEYS):
        return None
    normalized = {key: enum_value(snapshot.get(key)) for key in TOOL_METADATA_KEYS}
    for required_key in ("tool_name", "source_type", "danger_level"):
        if not str(normalized.get(required_key) or "").strip():
            return None
    return normalized


def compact_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in metadata.items()
        if value is not None and not isinstance(value, (bytes, bytearray))
    }


def trace_ref(request: RunHarnessToolExecutionRequest) -> RunHarnessTraceRef:
    return RunHarnessTraceRef(trace_id=request.envelope.trace_id)


def enum_value(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    return value


def first_reason(admission: ToolAdmissionResult) -> str:
    return admission.reason_codes[0] if admission.reason_codes else "unknown"
