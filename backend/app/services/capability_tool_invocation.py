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


def _snapshot_payload(value: Any) -> dict[str, Any] | None:
    if isinstance(value, Mapping):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        payload = model_dump(mode="json")
        if isinstance(payload, Mapping):
            return dict(payload)
    return None


def build_capability_execution_context(
    arguments: Mapping[str, Any],
    *,
    admission_snapshot: Any = None,
) -> CapabilityExecutionContext:
    """Derive immutable identity context from the verified admission receipt."""
    raw_snapshot = (
        admission_snapshot
        if admission_snapshot is not None
        else arguments.get("execution_admission_snapshot")
    )
    snapshot_payload = _snapshot_payload(raw_snapshot)
    snapshot = (
        MappingProxyType(snapshot_payload)
        if snapshot_payload is not None
        else None
    )
    snapshot_payload = snapshot_payload or {}
    root_execution_id = _optional_string(
        snapshot_payload.get("root_execution_id")
        or arguments.get("root_execution_id")
    )
    return CapabilityExecutionContext(
        workspace_id=_optional_string(
            snapshot_payload.get("workspace_id")
            or arguments.get("workspace_id")
        ),
        project_id=_optional_string(arguments.get("project_id")),
        execution_id=_optional_string(
            arguments.get("execution_id") or root_execution_id
        ),
        root_execution_id=root_execution_id,
        trace_id=_optional_string(
            snapshot_payload.get("trace_id")
            or arguments.get("trace_id")
            or root_execution_id
        ),
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
    *,
    execution_context: CapabilityExecutionContext | None = None,
) -> Any:
    """Invoke a standard tool through `(inputs, ctx)` or preserve legacy kwargs."""
    copied_arguments = dict(arguments)
    if uses_standard_tool_signature(func):
        return func(
            inputs=copied_arguments,
            ctx=execution_context
            or build_capability_execution_context(copied_arguments),
        )
    return func(**copied_arguments)


async def invoke_capability_tool_async(
    func: Callable[..., Any],
    arguments: Mapping[str, Any],
    *,
    execution_context: CapabilityExecutionContext | None = None,
) -> Any:
    """Await either standard or legacy capability tool results."""
    result = invoke_capability_tool(
        func,
        arguments,
        execution_context=execution_context,
    )
    if inspect.isawaitable(result):
        return await result
    return result
