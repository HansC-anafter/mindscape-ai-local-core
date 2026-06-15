"""Runner lifecycle hooks — generic on_fail hook invocation."""

import asyncio
import inspect
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _resolve_tool_backend_ref(tool_slot: str) -> str | None:
    """Resolve a lifecycle hook tool slot into a Python backend reference."""
    if ":" in tool_slot:
        return tool_slot
    if "." not in tool_slot:
        return None

    try:
        from backend.app.services.capability_registry import (
            get_tool_backend,
            load_capabilities,
        )
    except Exception:
        return None

    parts = tool_slot.split(".", 1)
    if len(parts) != 2:
        return None

    backend_ref = get_tool_backend(parts[0], parts[1])
    if backend_ref:
        return backend_ref

    try:
        load_capabilities()
    except Exception:
        return None

    return get_tool_backend(parts[0], parts[1])


async def _invoke_on_fail_hook(
    execution_context: Dict[str, Any],
    failure_reason: str,
    task_id: str,
) -> bool:
    """Invoke the on_fail lifecycle hook if declared in execution_context.

    This is a GENERIC mechanism -- no pack-specific logic. The playbook spec
    declares which tool to call and how to map inputs. The runner just
    resolves and invokes.

    Returns True if the hook was invoked (regardless of outcome), False if
    no on_fail hook is declared.
    """
    hooks = execution_context.get("lifecycle_hooks")
    if not isinstance(hooks, dict):
        return False
    on_fail = hooks.get("on_fail")
    if not isinstance(on_fail, dict):
        return False

    tool_slot = on_fail.get("tool_slot")
    inputs_map = on_fail.get("inputs_map", {})
    if not tool_slot:
        return False

    # Resolve inputs_map templates
    ctx_inputs = execution_context.get("inputs", {})
    if not isinstance(ctx_inputs, dict):
        ctx_inputs = {}

    resolved = {}
    for param_name, template in inputs_map.items():
        if not isinstance(template, str):
            resolved[param_name] = template
            continue
        if template.startswith("{{input.") and template.endswith("}}"):
            key = template[len("{{input.") : -len("}}")].strip()
            resolved[param_name] = ctx_inputs.get(key)
        elif template.startswith("{{context.") and template.endswith("}}"):
            key = template[len("{{context.") : -len("}}")].strip()
            if key == "task_id":
                resolved[param_name] = task_id
            elif key == "error":
                resolved[param_name] = failure_reason
            else:
                resolved[param_name] = execution_context.get(key)
        else:
            resolved[param_name] = template

    # Pass full execution_context so the hook tool has all the info it needs
    resolved["execution_context"] = execution_context

    try:
        import importlib

        backend_ref = None

        backend_ref = _resolve_tool_backend_ref(tool_slot)

        if not backend_ref:
            logger.warning(
                f"on_fail hook: tool_slot '{tool_slot}' not found in registry"
            )
            return False

        module_path, func_name = backend_ref.rsplit(":", 1)
        mod = importlib.import_module(module_path)
        func = getattr(mod, func_name)
        result = func(**resolved)
        if inspect.isawaitable(result):
            result = await result
        logger.info(
            f"on_fail hook invoked: {tool_slot} for task {task_id} " f"result={result}"
        )
        return True
    except Exception as e:
        logger.warning(f"on_fail hook failed (non-fatal): {e}")
        return False


def _invoke_on_fail_hook_sync(
    execution_context: Dict[str, Any],
    failure_reason: str,
    task_id: str,
) -> bool:
    """Invoke the async lifecycle hook helper from synchronous runner paths."""
    return asyncio.run(
        _invoke_on_fail_hook(
            execution_context=execution_context,
            failure_reason=failure_reason,
            task_id=task_id,
        )
    )
