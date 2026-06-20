"""Result status helpers for PlaybookRunExecutor."""

from typing import Any, Dict, Optional


def is_terminal_failure_status(value: Any) -> bool:
    """Return whether a status value represents a terminal failure."""
    return str(value or "").strip().lower() in {"error", "failed"}


def workflow_outputs_has_errors(outputs: Any) -> bool:
    """Detect workflow output payloads that carry failure markers."""
    if not isinstance(outputs, dict):
        return False
    if is_terminal_failure_status(outputs.get("status")):
        return True
    return str(outputs.get("analysis_status") or "").strip().lower() == "failed"


def workflow_result_has_errors(result: Optional[Dict[str, Any]]) -> bool:
    """Detect terminal workflow errors even when the wrapper status is completed."""
    if not isinstance(result, dict):
        return False

    if is_terminal_failure_status(result.get("status")):
        return True

    if workflow_outputs_has_errors(result.get("outputs")):
        return True

    steps = result.get("steps")
    if isinstance(steps, dict):
        for step_result in steps.values():
            if workflow_result_has_errors(step_result):
                return True

    context = result.get("context")
    if isinstance(context, dict):
        for context_result in context.values():
            if workflow_result_has_errors(context_result):
                return True
    return False


def runtime_result_has_errors(
    runtime_result: Any,
    raw_result: Optional[Dict[str, Any]] = None,
) -> bool:
    """Detect step-level runtime failures from raw workflow payload or metadata."""
    if workflow_result_has_errors(raw_result):
        return True

    if runtime_result is None:
        return False

    if getattr(runtime_result, "status", None) == "failed":
        return True

    metadata = getattr(runtime_result, "metadata", None)
    if not isinstance(metadata, dict):
        return False

    if workflow_outputs_has_errors(metadata.get("outputs")):
        return True

    steps = metadata.get("steps")
    if isinstance(steps, dict):
        for step_result in steps.values():
            if workflow_result_has_errors(step_result):
                return True

    workflow_result = metadata.get("workflow_result")
    if isinstance(workflow_result, dict) and workflow_result_has_errors(
        workflow_result
    ):
        return True

    return False
