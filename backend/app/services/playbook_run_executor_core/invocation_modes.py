"""Invocation-mode helpers for PlaybookRunExecutor."""

import logging
from typing import Any, Awaitable, Callable, Dict, Optional

from backend.app.models.playbook import InvocationTolerance

logger = logging.getLogger(__name__)


def merge_plan_node_inputs(
    *,
    playbook_code: str,
    inputs: Optional[Dict[str, Any]],
    context: Any,
) -> Optional[Dict[str, Any]]:
    """Merge plan-provided data into invocation inputs for plan-node execution."""
    plan_data = None
    if context.visible_state:
        plan_data = context.visible_state.get("fromPlan") or context.visible_state.get(
            "plan_data"
        )

    if not plan_data and context.strategy.tolerance == InvocationTolerance.STRICT:
        error_msg = (
            f"Plan input insufficient for playbook {playbook_code}. "
            f"Required data not provided by upstream tasks."
        )
        logger.error("PlaybookRunExecutor: %s", error_msg)
        raise ValueError(error_msg)

    if not plan_data:
        return inputs

    merged_inputs = dict(inputs or {})
    merged_inputs.update(plan_data)
    logger.info(
        "PlaybookRunExecutor: Merged plan data into inputs for %s",
        playbook_code,
    )
    return merged_inputs


async def execute_conversation_invocation(
    *,
    playbook_code: str,
    profile_id: str,
    inputs: Optional[Dict[str, Any]],
    workspace_id: Optional[str],
    project_id: Optional[str],
    target_language: Optional[str],
    variant_id: Optional[str],
    invocation_mode: str,
    context: Any,
    start_playbook_execution_fn: Callable[..., Awaitable[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Execute conversation-mode playbook for standalone or plan-node invocation."""
    if invocation_mode == "standalone":
        logger.info(
            "PlaybookRunExecutor: Executing conversation in standalone mode "
            "(max_lookup_rounds=%s)",
            context.strategy.max_lookup_rounds,
        )
    else:
        logger.info(
            "PlaybookRunExecutor: Executing conversation in plan_node mode "
            "(plan_id=%s, task_id=%s)",
            context.plan_id,
            context.task_id,
        )

    result = await start_playbook_execution_fn(
        playbook_code=playbook_code,
        profile_id=profile_id,
        inputs=inputs,
        workspace_id=workspace_id,
        project_id=project_id,
        target_language=target_language,
        variant_id=variant_id,
    )

    response = {
        "execution_mode": "conversation",
        "playbook_code": playbook_code,
        "result": result,
        "has_json": False,
        "invocation_mode": invocation_mode,
    }
    if invocation_mode == "plan_node":
        response["plan_id"] = context.plan_id
        response["task_id"] = context.task_id
    return response
