"""Step-dispatch helpers for workflow execution."""

import logging
import os
from typing import Any, Awaitable, Callable, Dict, Optional

from backend.app.services.tool_slot_resolver import (
    SlotNotFoundError,
    get_tool_slot_resolver,
)
from backend.app.services.workflow.result_mapper import (
    map_sub_playbook_result_to_step_outputs,
)

logger = logging.getLogger(__name__)


async def resolve_tool_slot_to_tool_id(
    *,
    step: Any,
    store: Any,
    workspace_id: Optional[str],
    project_id: Optional[str],
) -> str:
    """Resolve a workflow step tool slot to a concrete tool id."""
    slot_resolver = get_tool_slot_resolver(store=store)
    try:
        tool_id = await slot_resolver.resolve(
            slot=step.tool_slot,
            workspace_id=workspace_id or "",
            project_id=project_id,
        )
        logger.info(
            "Resolved tool slot '%s' to tool '%s'",
            step.tool_slot,
            tool_id,
        )
        return tool_id
    except SlotNotFoundError as exc:
        logger.error("Failed to resolve tool slot '%s': %s", step.tool_slot, exc)
        raise ValueError(
            f"Tool slot '{step.tool_slot}' not configured. Please set up a mapping in workspace settings."
        ) from exc


async def execute_playbook_slot(
    *,
    step: Any,
    current_depth: int,
    resolved_inputs: Dict[str, Any],
    execution_id: Optional[str],
    workspace_id: Optional[str],
    profile_id: Optional[str],
    project_id: Optional[str],
    load_playbook_json_fn: Callable[[str], Any],
    execute_playbook_steps_fn: Callable[..., Awaitable[Dict[str, Any]]],
    max_depth: int = 3,
) -> Dict[str, Any]:
    """Execute a playbook_slot step via recursive sub-playbook dispatch."""
    if os.getenv("ENABLE_PLAYBOOK_SLOT_RUNTIME", "false").lower() != "true":
        raise ValueError(
            f"Step '{step.id}' uses playbook_slot '{step.playbook_slot}' "
            f"but runtime dispatch is not enabled. "
            f"Set ENABLE_PLAYBOOK_SLOT_RUNTIME=true to enable."
        )

    if current_depth >= max_depth:
        raise ValueError(
            f"playbook_slot nesting depth exceeded max={max_depth} "
            f"at step '{step.id}' -> '{step.playbook_slot}'"
        )

    sub_playbook_json = load_playbook_json_fn(step.playbook_slot)
    if not sub_playbook_json:
        raise ValueError(
            f"Sub-playbook '{step.playbook_slot}' not found for "
            f"playbook_slot step '{step.id}'"
        )

    logger.info(
        "playbook_slot dispatch: step '%s' -> sub-playbook '%s' (depth=%s)",
        step.id,
        step.playbook_slot,
        current_depth + 1,
    )

    sub_result = await execute_playbook_steps_fn(
        sub_playbook_json,
        resolved_inputs,
        execution_id=execution_id,
        workspace_id=workspace_id,
        profile_id=profile_id,
        project_id=project_id,
    )
    return map_sub_playbook_result_to_step_outputs(step.outputs, sub_result)
