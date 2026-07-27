"""Single invocation seam for standard and legacy capability tool signatures."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Mapping


@dataclass(frozen=True)
class CapabilityExecutionContext:
    """Read-only execution identity exposed to standard capability tools."""

    workspace_id: str | None
    project_id: str | None
    execution_id: str | None
    root_execution_id: str | None
    trace_id: str | None
    profile_id: str | None
    admission_snapshot: Mapping[str, Any] | None


def _optional_string(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def build_capability_execution_context(
    arguments: Mapping[str, Any],
) -> CapabilityExecutionContext:
    """Derive immutable identity context without changing tool arguments."""
    raw_snapshot = arguments.get("execution_admission_snapshot")
    snapshot = (
        MappingProxyType(dict(raw_snapshot))
        if isinstance(raw_snapshot, dict)
        else None
    )
    return CapabilityExecutionContext(
        workspace_id=_optional_string(arguments.get("workspace_id")),
        project_id=_optional_string(arguments.get("project_id")),
        execution_id=_optional_string(arguments.get("execution_id")),
        root_execution_id=_optional_string(arguments.get("root_execution_id")),
        trace_id=_optional_string(arguments.get("trace_id")),
        profile_id=_optional_string(
            arguments.get("profile_id") or arguments.get("actor_user_id")
        ),
        admission_snapshot=snapshot,
    )


def uses_standard_tool_signature(func: Callable[..., Any]) -> bool:
    """Return whether a callable explicitly declares the `(inputs, ctx)` seam."""
    parameters = inspect.signature(func).parameters
    return "inputs" in parameters and "ctx" in parameters


def invoke_capability_tool(
    func: Callable[..., Any],
    arguments: Mapping[str, Any],
) -> Any:
    """Invoke a standard tool through `(inputs, ctx)` or preserve legacy kwargs."""
    copied_arguments = dict(arguments)
    if uses_standard_tool_signature(func):
        return func(
            inputs=copied_arguments,
            ctx=build_capability_execution_context(copied_arguments),
        )
    return func(**copied_arguments)


async def invoke_capability_tool_async(
    func: Callable[..., Any],
    arguments: Mapping[str, Any],
) -> Any:
    """Await either standard or legacy capability tool results."""
    result = invoke_capability_tool(func, arguments)
    if inspect.isawaitable(result):
        return await result
    return result
