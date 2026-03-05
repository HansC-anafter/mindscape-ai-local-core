"""
Step lifecycle hook invoker for workflow orchestrator.

Thin service-layer adapter that wraps execution_hooks.async_invoke_lifecycle_hook.
Provides _invoke_step_hook() to avoid direct routes-layer imports from services.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


async def invoke_step_hook(
    hook_name: str,
    hook_spec_model: Any,
    playbook_inputs: Dict[str, Any],
    execution_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    profile_id: Optional[str] = None,
    step_id: Optional[str] = None,
    step_outputs: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    """Invoke a step-level lifecycle hook.

    Wraps async_invoke_lifecycle_hook from execution_hooks with a
    service-layer API that the orchestrator can call directly.

    Args:
        hook_name: Human-readable name (e.g. "pre_step:ocr")
        hook_spec_model: HookSpec pydantic model instance
        playbook_inputs: Playbook-level inputs
        execution_id: Current execution ID
        workspace_id: Current workspace ID
        profile_id: Current profile ID
        step_id: Current step ID
        step_outputs: Completed step outputs for {{step.*}} templates
        error: Error message (for on_error hooks)
    """
    from backend.app.routes.core.execution_hooks import (
        async_invoke_lifecycle_hook,
    )

    hook_context = {
        "execution_id": execution_id or "",
        "workspace_id": workspace_id or "",
        "profile_id": profile_id or "",
    }
    if step_id:
        hook_context["step_id"] = step_id
    if error:
        hook_context["error"] = error

    await async_invoke_lifecycle_hook(
        hook_name=hook_name,
        hook_spec=hook_spec_model.model_dump(),
        normalized_inputs=playbook_inputs,
        execution_context=hook_context,
        step_outputs=step_outputs,
    )
