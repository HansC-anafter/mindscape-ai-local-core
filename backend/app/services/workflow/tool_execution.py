"""Tool-execution helpers for workflow execution."""

import logging
from typing import Any, Awaitable, Callable, Dict, Optional

from backend.app.services.execution_core.errors import RecoverableStepError
from backend.app.services.tool_policy_engine import (
    PolicyViolationError,
    get_tool_policy_engine,
)

logger = logging.getLogger(__name__)


def is_llm_tool(tool_id: str) -> bool:
    """Return whether a tool id should receive LLM-specific inputs."""
    return tool_id.startswith("core_llm.") or "llm" in tool_id.lower()


def check_tool_policy(
    *,
    step: Any,
    tool_id: str,
    workspace_id: Optional[str],
) -> None:
    """Validate tool execution against an optional step-level policy."""
    if not (hasattr(step, "tool_policy") and step.tool_policy):
        return

    policy_engine = get_tool_policy_engine()
    try:
        policy_engine.check(
            tool_id=tool_id,
            policy=step.tool_policy,
            workspace_id=workspace_id,
        )
    except PolicyViolationError as exc:
        logger.error("Tool '%s' violates policy: %s", tool_id, exc)
        raise ValueError(f"Tool execution blocked by policy: {str(exc)}") from exc


def build_tool_inputs(
    *,
    tool_id: str,
    resolved_inputs: Dict[str, Any],
    profile_id: Optional[str],
    model_override: Optional[str],
) -> Dict[str, Any]:
    """Build the concrete tool input payload for a single workflow step."""
    tool_inputs = resolved_inputs.copy()

    if profile_id and is_llm_tool(tool_id):
        tool_inputs["profile_id"] = profile_id

    if model_override:
        tool_inputs["_model_override"] = model_override

    return tool_inputs


def normalize_tool_result(
    *,
    step_id: str,
    tool_result: Any,
) -> Any:
    """Convert tool error payloads into workflow exceptions."""
    if isinstance(tool_result, dict) and tool_result.get("status") == "error":
        error_msg = tool_result.get("error", "Unknown tool error")
        if tool_result.get("recoverable"):
            raise RecoverableStepError(
                step_id,
                error_type=tool_result.get("error_type", "recoverable"),
                detail=error_msg,
            )
        raise ValueError(f"Step {step_id} tool error: {error_msg}")

    return tool_result


async def execute_tool_step(
    *,
    step: Any,
    tool_id: str,
    resolved_inputs: Dict[str, Any],
    playbook_inputs: Optional[Dict[str, Any]],
    execution_profile: Optional[Dict[str, Any]],
    execution_id: Optional[str],
    workspace_id: Optional[str],
    profile_id: Optional[str],
    resolve_remote_tool_route_fn: Callable[..., Optional[Dict[str, Any]]],
    resolve_tool_model_override_fn: Callable[..., Optional[str]],
    maybe_execute_tool_via_remote_route_fn: Callable[..., Awaitable[tuple[bool, Any]]],
    execute_tool_fn: Callable[..., Awaitable[Any]],
) -> Any:
    """Execute a workflow tool step using local or remote dispatch."""
    playbook_inputs = playbook_inputs or {}

    check_tool_policy(
        step=step,
        tool_id=tool_id,
        workspace_id=workspace_id,
    )

    remote_route = resolve_remote_tool_route_fn(
        playbook_inputs,
        step_id=step.id,
        tool_id=tool_id,
    )
    model_override = resolve_tool_model_override_fn(
        tool_id=tool_id,
        playbook_inputs=playbook_inputs,
        remote_route=remote_route,
        execution_profile=execution_profile,
    )
    tool_inputs = build_tool_inputs(
        tool_id=tool_id,
        resolved_inputs=resolved_inputs,
        profile_id=profile_id,
        model_override=model_override,
    )

    handled_remotely, remote_tool_result = (
        await maybe_execute_tool_via_remote_route_fn(
            step_id=step.id,
            tool_id=tool_id,
            tool_inputs=tool_inputs,
            playbook_inputs=playbook_inputs,
            execution_id=execution_id,
            workspace_id=workspace_id,
        )
    )
    if handled_remotely:
        return normalize_tool_result(
            step_id=step.id,
            tool_result=remote_tool_result,
        )

    tool_result = await execute_tool_fn(tool_id, **tool_inputs)
    return normalize_tool_result(
        step_id=step.id,
        tool_result=tool_result,
    )
