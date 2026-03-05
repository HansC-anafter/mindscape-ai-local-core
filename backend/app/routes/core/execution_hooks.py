"""
Lifecycle hook invoker for playbook execution.

Extracted from playbook_execution.py. Provides a generic mechanism
to invoke tool-slot hooks declared in playbook specs (e.g. on_queue).
"""

import importlib
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def invoke_lifecycle_hook(
    hook_name: str,
    hook_spec: Dict[str, Any],
    normalized_inputs: Dict[str, Any],
    execution_context: Dict[str, Any],
) -> None:
    """Invoke a lifecycle hook declared in a playbook spec.

    This is a GENERIC mechanism -- no pack-specific logic.
    The playbook spec declares which tool to call and how to map inputs.

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

    # Resolve inputs_map: replace {{input.xxx}} and {{context.xxx}} templates
    resolved = {}
    for param_name, template in inputs_map.items():
        if not isinstance(template, str):
            resolved[param_name] = template
            continue
        if template.startswith("{{input.") and template.endswith("}}"):
            key = template[len("{{input.") : -len("}}")].strip()
            resolved[param_name] = normalized_inputs.get(key)
        elif template.startswith("{{context.") and template.endswith("}}"):
            key = template[len("{{context.") : -len("}}")].strip()
            resolved[param_name] = execution_context.get(key)
        else:
            resolved[param_name] = template

    # Dynamic import: tool_slot format is "capability.tool_name"
    # e.g. "ig.register_seed_immediately" -> capability="ig", tool="register_seed_immediately"
    # or direct Python path: "capabilities.ig.tools.module:function_name"
    try:
        backend_ref = None

        # Strategy 1: capability registry lookup (tool_slot = "cap.tool")
        if ":" not in tool_slot and "." in tool_slot:
            try:
                from backend.app.capabilities.registry import get_tool_backend

                parts = tool_slot.split(".", 1)
                if len(parts) == 2:
                    backend_ref = get_tool_backend(parts[0], parts[1])
            except Exception:
                pass

        # Strategy 2: direct Python import path (tool_slot = "module:func")
        if not backend_ref and ":" in tool_slot:
            backend_ref = tool_slot

        if not backend_ref:
            logger.warning(
                f"Lifecycle hook '{hook_name}': tool_slot '{tool_slot}' not found "
                f"in capability registry"
            )
            return

        module_path, func_name = backend_ref.rsplit(":", 1)
        mod = importlib.import_module(module_path)
        func = getattr(mod, func_name)
        func(**resolved)
        logger.info(
            f"Lifecycle hook '{hook_name}' invoked: {tool_slot} "
            f"with {list(resolved.keys())}"
        )
    except Exception as e:
        logger.warning(f"Lifecycle hook '{hook_name}' failed (non-fatal): {e}")
