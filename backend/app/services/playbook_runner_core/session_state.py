"""Session-state helpers for playbook runner."""

import logging
from typing import Any, Awaitable, Callable, Dict

logger = logging.getLogger(__name__)


async def get_or_restore_conversation_manager(
    *,
    execution_id: str,
    active_conversations: Dict[str, Any],
    restore_execution_state_fn: Callable[[str], Awaitable[Any]],
) -> Any:
    """Return an in-memory conversation manager or restore it from state."""
    conv_manager = active_conversations.get(execution_id)
    if conv_manager:
        return conv_manager

    logger.info(
        "Execution %s not in memory, attempting to restore from database",
        execution_id,
    )
    conv_manager = await restore_execution_state_fn(execution_id)
    if conv_manager:
        active_conversations[execution_id] = conv_manager
        logger.info("Successfully restored execution %s from database", execution_id)
        return conv_manager

    raise ValueError(f"Execution not found: {execution_id}")


def preserve_sandbox_id_in_execution_context(
    *,
    execution_id: str,
    sandbox_id: str,
    get_task_by_execution_id_fn: Callable[[str], Any],
    update_task_fn: Callable[[str, Dict[str, Any]], Any],
) -> bool:
    """Persist sandbox_id onto the task execution context for the session."""
    task = get_task_by_execution_id_fn(execution_id)
    if not task:
        return False

    execution_context = task.execution_context or {}
    execution_context["sandbox_id"] = sandbox_id
    update_task_fn(task.id, execution_context)
    return True


def get_playbook_execution_result(
    *,
    execution_id: str,
    active_conversations: Dict[str, Any],
) -> Any:
    """Return the final structured output or completion sentinel for an execution."""
    conv_manager = active_conversations.get(execution_id)
    if not conv_manager:
        return {
            "status": "completed",
            "execution_id": execution_id,
            "note": "Execution completed (conversation mode, no structured output)",
        }

    if conv_manager.extracted_data:
        return conv_manager.extracted_data

    return None


def cleanup_execution(
    *,
    execution_id: str,
    active_conversations: Dict[str, Any],
) -> None:
    """Remove a completed execution from in-memory conversations."""
    if execution_id in active_conversations:
        del active_conversations[execution_id]


def list_active_execution_ids(active_conversations: Dict[str, Any]) -> list[str]:
    """List active in-memory execution ids."""
    return list(active_conversations.keys())
