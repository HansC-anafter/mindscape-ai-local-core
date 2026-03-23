"""Workflow-step execution helpers."""

import logging
from typing import Any, Awaitable, Callable, Dict, Optional

from backend.app.models.playbook import InteractionMode, PlaybookKind

logger = logging.getLogger(__name__)


def merge_workflow_context_into_inputs(
    *,
    playbook_code: str,
    resolved_inputs: Dict[str, Any],
    workflow_context: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge workflow context into resolved inputs without overwriting explicit values."""
    merged_inputs = dict(resolved_inputs)
    if workflow_context:
        for key, value in workflow_context.items():
            if key not in merged_inputs:
                merged_inputs[key] = value
        logger.info(
            "WorkflowOrchestrator.execute_workflow_step: Merged workflow_context into resolved_inputs for %s. Keys: %s",
            playbook_code,
            list(merged_inputs.keys()),
        )
    return merged_inputs


async def execute_workflow_step(
    *,
    step: Any,
    workflow_context: Dict[str, Any],
    previous_results: Dict[str, Dict[str, Any]],
    execution_id: Optional[str],
    workspace_id: Optional[str],
    profile_id: Optional[str],
    project_id: Optional[str],
    load_playbook_json_fn: Callable[[str], Any],
    prepare_workflow_step_inputs_fn: Callable[[Any, Dict[str, Dict[str, Any]], Dict[str, Any]], Dict[str, Any]],
    execute_playbook_steps_fn: Callable[..., Awaitable[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Execute a single workflow step after resolving its inputs and mode."""
    playbook_json = load_playbook_json_fn(step.playbook_code)
    if not playbook_json:
        raise ValueError(f"playbook.json not found for {step.playbook_code}")

    resolved_inputs = prepare_workflow_step_inputs_fn(
        step,
        previous_results,
        workflow_context,
    )
    resolved_inputs = merge_workflow_context_into_inputs(
        playbook_code=step.playbook_code,
        resolved_inputs=resolved_inputs,
        workflow_context=workflow_context,
    )

    if step.kind == PlaybookKind.USER_WORKFLOW and (
        InteractionMode.NEEDS_REVIEW in step.interaction_mode
    ):
        logger.info("Step %s requires review", step.playbook_code)

    if step.kind not in (PlaybookKind.SYSTEM_TOOL, PlaybookKind.USER_WORKFLOW):
        raise ValueError(f"Unknown playbook kind: {step.kind}")

    return await execute_playbook_steps_fn(
        playbook_json,
        resolved_inputs,
        execution_id,
        workspace_id,
        profile_id,
        project_id,
    )
