"""
Pipeline Playbook -- Post-response playbook trigger logic.

Handles hybrid mode Part1/Part2 parsing and execution mode
playbook detection after LLM response generation.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def handle_post_response_playbook(
    execution_mode: str,
    message: str,
    workspace: Any,
    workspace_id: str,
    profile_id: str,
    profile: Any,
    store: Any,
    result: Any,
) -> Any:
    """Handle post-response playbook decisions.

    Routes to hybrid or execution playbook handler based on mode.

    Args:
        execution_mode: qa | execution | hybrid.
        message: Original user message.
        workspace: Workspace object.
        workspace_id: Workspace ID.
        profile_id: Profile ID.
        profile: UserProfile object.
        store: MindscapeStore instance.
        result: PipelineResult accumulator.

    Returns:
        Updated PipelineResult.
    """
    full_text = result.response_text

    if execution_mode == "hybrid":
        return await _handle_hybrid_playbook(
            full_text,
            message,
            workspace_id,
            profile_id,
            profile,
            store,
            result,
        )
    elif execution_mode == "execution":
        return await _handle_execution_playbook(
            full_text,
            workspace,
            workspace_id,
            profile_id,
            execution_mode,
            result,
        )

    return result


async def _handle_hybrid_playbook(
    full_text: str,
    message: str,
    workspace_id: str,
    profile_id: str,
    profile: Any,
    store: Any,
    result: Any,
) -> Any:
    """Handle hybrid mode: parse Part1/Part2 and execute playbook."""
    from backend.app.services.conversation.response_parser import (
        parse_agent_mode_response,
    )
    from backend.features.workspace.chat.playbook.executor import (
        execute_playbook_for_hybrid_mode,
    )

    parsed = parse_agent_mode_response(full_text)
    logger.info(
        f"[PipelineCore] Hybrid parse - Part1: {len(parsed['part1'])}, "
        f"Part2: {len(parsed['part2'])}, "
        f"Tasks: {len(parsed['executable_tasks'])}"
    )

    if parsed["executable_tasks"]:
        try:
            execution_result = await execute_playbook_for_hybrid_mode(
                message=message,
                executable_tasks=parsed["executable_tasks"],
                workspace_id=workspace_id,
                profile_id=profile_id,
                profile=profile,
                store=store,
            )
            if execution_result:
                result.playbook_code = execution_result.get("playbook_code")
                result.execution_id = execution_result.get("execution_id")
                logger.info(
                    f"[PipelineCore] Hybrid playbook executed: "
                    f"{result.playbook_code}"
                )
        except Exception as e:
            logger.warning(
                f"[PipelineCore] Hybrid playbook execution error: {e}",
                exc_info=True,
            )

    return result


async def _handle_execution_playbook(
    full_text: str,
    workspace: Any,
    workspace_id: str,
    profile_id: str,
    execution_mode: str,
    result: Any,
) -> Any:
    """Handle execution mode: check for playbook trigger."""
    from backend.features.workspace.chat.playbook.trigger import (
        check_and_trigger_playbook,
    )

    try:
        trigger_result = await check_and_trigger_playbook(
            full_text=full_text,
            workspace=workspace,
            workspace_id=workspace_id,
            profile_id=profile_id,
            execution_mode=execution_mode,
        )
        if trigger_result:
            result.playbook_code = trigger_result.get("playbook_code")
            result.execution_id = trigger_result.get("execution_id")
            logger.info(
                f"[PipelineCore] Execution playbook triggered: "
                f"{result.playbook_code}"
            )
    except Exception as e:
        logger.warning(
            f"[PipelineCore] Execution playbook error: {e}",
            exc_info=True,
        )

    return result
