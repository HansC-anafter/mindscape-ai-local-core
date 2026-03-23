"""
Lifecycle hook invoker for playbook execution.

Extracted from playbook_execution.py. Provides a generic mechanism
to invoke tool-slot hooks declared in playbook specs (e.g. on_queue).

Supports both sync (route-layer) and async (step-level) invocation.
"""

import asyncio
import importlib
import inspect
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def _resolve_template(
    template: str,
    normalized_inputs: Dict[str, Any],
    execution_context: Dict[str, Any],
    step_outputs: Optional[Dict[str, Any]] = None,
) -> Any:
    """Resolve a single template string against available contexts.

    Supported namespaces:
        {{input.key}}   - from normalized_inputs
        {{context.key}} - from execution_context
        {{step.step_id.field}} - from step_outputs (P3-4b)
    """
    if not isinstance(template, str):
        return template

    if template.startswith("{{input.") and template.endswith("}}"):
        key = template[len("{{input.") : -len("}}")].strip()
        return normalized_inputs.get(key)
    elif template.startswith("{{context.") and template.endswith("}}"):
        key = template[len("{{context.") : -len("}}")].strip()
        return execution_context.get(key)
    elif template.startswith("{{step.") and template.endswith("}}"):
        # {{step.step_id.field}} -> step_outputs["step_id"]["field"]
        if step_outputs is None:
            return None
        path = template[len("{{step.") : -len("}}")].strip()
        parts = path.split(".", 1)
        if len(parts) == 2:
            step_id, field = parts
            step_data = step_outputs.get(step_id, {})
            if isinstance(step_data, dict):
                return step_data.get(field)
        return None
    else:
        return template


def _resolve_inputs_map(
    inputs_map: Dict[str, Any],
    normalized_inputs: Dict[str, Any],
    execution_context: Dict[str, Any],
    step_outputs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Resolve all template values in an inputs_map."""
    resolved = {}
    for param_name, template in inputs_map.items():
        resolved[param_name] = _resolve_template(
            template, normalized_inputs, execution_context, step_outputs
        )
    return resolved


def _resolve_backend_ref(tool_slot: str) -> Optional[str]:
    """Resolve a tool_slot to a backend reference (module:function).

    Strategy 1: capability registry lookup (tool_slot = "cap.tool")
    Strategy 2: direct Python import path (tool_slot = "module:func")
    """
    backend_ref = None

    # Strategy 1: capability registry lookup
    if ":" not in tool_slot and "." in tool_slot:
        try:
            from backend.app.services.capability_registry import get_tool_backend

            parts = tool_slot.split(".", 1)
            if len(parts) == 2:
                backend_ref = get_tool_backend(parts[0], parts[1])
        except Exception:
            pass

    # Strategy 2: direct Python import path
    if not backend_ref and ":" in tool_slot:
        backend_ref = tool_slot

    return backend_ref


def resolve_inputs_map(
    inputs_map: Dict[str, Any],
    normalized_inputs: Dict[str, Any],
    execution_context: Dict[str, Any],
    step_outputs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Public wrapper for resolving templated tool inputs."""
    return _resolve_inputs_map(
        inputs_map, normalized_inputs, execution_context, step_outputs
    )


def invoke_tool_slot(tool_slot: str, resolved_inputs: Dict[str, Any]) -> Any:
    """Invoke a resolved tool slot synchronously and return the tool result."""
    backend_ref = _resolve_backend_ref(tool_slot)
    if not backend_ref:
        raise ValueError(f"Tool slot '{tool_slot}' not found in capability registry")

    module_path, func_name = backend_ref.rsplit(":", 1)
    mod = importlib.import_module(module_path)
    func = getattr(mod, func_name)
    if inspect.iscoroutinefunction(func):
        raise RuntimeError(
            f"Tool slot '{tool_slot}' is async; use async_invoke_tool_slot instead"
        )
    return func(**resolved_inputs)


async def async_invoke_tool_slot(tool_slot: str, resolved_inputs: Dict[str, Any]) -> Any:
    """Invoke a resolved tool slot and return the tool result."""
    backend_ref = _resolve_backend_ref(tool_slot)
    if not backend_ref:
        raise ValueError(f"Tool slot '{tool_slot}' not found in capability registry")

    module_path, func_name = backend_ref.rsplit(":", 1)
    mod = importlib.import_module(module_path)
    func = getattr(mod, func_name)

    if inspect.iscoroutinefunction(func):
        return await func(**resolved_inputs)
    return await asyncio.to_thread(func, **resolved_inputs)


def invoke_lifecycle_hook(
    hook_name: str,
    hook_spec: Dict[str, Any],
    normalized_inputs: Dict[str, Any],
    execution_context: Dict[str, Any],
) -> None:
    """Invoke a lifecycle hook (sync, route-layer).

    Backward-compatible entry point used by playbook_execution.py on_queue.

    Hook spec format:
        {
            "tool_slot": "ig.register_seed_immediately",
            "inputs_map": {
                "seed": "{{input.target_username}}",
                "workspace_id": "{{input.workspace_id}}"
            }
        }
    """
    tool_slot = hook_spec.get("tool_slot")
    inputs_map = hook_spec.get("inputs_map", {})
    if not tool_slot:
        return

    resolved = resolve_inputs_map(inputs_map, normalized_inputs, execution_context)

    try:
        invoke_tool_slot(tool_slot, resolved)
        logger.info(
            f"Lifecycle hook '{hook_name}' invoked: {tool_slot} "
            f"with {list(resolved.keys())}"
        )
    except ValueError as e:
        logger.warning(f"Lifecycle hook '{hook_name}' skipped (non-fatal): {e}")
    except Exception as e:
        logger.warning(f"Lifecycle hook '{hook_name}' failed (non-fatal): {e}")


async def async_invoke_lifecycle_hook(
    hook_name: str,
    hook_spec: Dict[str, Any],
    normalized_inputs: Dict[str, Any],
    execution_context: Dict[str, Any],
    step_outputs: Optional[Dict[str, Any]] = None,
) -> None:
    """Invoke a lifecycle hook (async, step-level).

    Supports {{step.*}} templates via step_outputs parameter.
    Handles both sync and async tool functions transparently.

    Args:
        hook_name: Human-readable hook name (e.g. "pre_step", "post_step")
        hook_spec: Dict with "tool_slot" and optional "inputs_map"
        normalized_inputs: Playbook-level inputs
        execution_context: Execution context (workspace_id, execution_id, etc.)
        step_outputs: Completed step outputs for {{step.*}} template resolution
    """
    tool_slot = hook_spec.get("tool_slot")
    inputs_map = hook_spec.get("inputs_map", {})
    if not tool_slot:
        return

    resolved = resolve_inputs_map(
        inputs_map, normalized_inputs, execution_context, step_outputs
    )

    try:
        await async_invoke_tool_slot(tool_slot, resolved)
        logger.info(
            f"Lifecycle hook '{hook_name}' invoked (async): {tool_slot} "
            f"with {list(resolved.keys())}"
        )
    except ValueError as e:
        logger.warning(f"Lifecycle hook '{hook_name}' skipped (non-fatal): {e}")
    except Exception as e:
        logger.warning(f"Lifecycle hook '{hook_name}' failed (non-fatal): {e}")
