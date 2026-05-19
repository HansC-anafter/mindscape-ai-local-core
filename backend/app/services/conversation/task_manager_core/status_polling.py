"""Async execution status polling helpers for TaskManager."""

from __future__ import annotations

import logging
from typing import Any, Optional

from backend.app.models.workspace import TaskStatus
from backend.app.services.conversation.task_manager_core.timeline_items import (
    create_failed_execution_timeline_item,
)
from backend.app.services.execution_core.clock import utc_now

logger = logging.getLogger(__name__)


async def check_and_update_task_status(
    *,
    manager: Any,
    task: Any,
    execution_id: Optional[str],
    playbook_code: str,
) -> None:
    """Check playbook execution status and update task and timeline stores."""
    try:
        if not execution_id:
            return

        if task.status in [TaskStatus.SUCCEEDED, TaskStatus.FAILED]:
            return

        try:
            execution_result_data = await _get_execution_result_data(
                manager=manager,
                task=task,
                execution_id=execution_id,
            )

            if execution_result_data:
                manager.tasks_store.update_task_status(
                    task_id=task.id,
                    status=TaskStatus.SUCCEEDED,
                    result=execution_result_data,
                    completed_at=utc_now(),
                )

                timeline_item = await manager.create_timeline_item_from_task(
                    task=task,
                    execution_result=execution_result_data,
                    playbook_code=playbook_code,
                )

                if timeline_item:
                    logger.info(
                        "Updated task %s from async execution %s, created timeline item %s",
                        task.id,
                        execution_id,
                        timeline_item.id,
                    )
                    manager._mark_task_notification_sent(task.id)
                else:
                    logger.warning("Failed to create timeline item for task %s", task.id)
            else:
                active_executions = (
                    manager.playbook_runner.list_active_executions()
                    if hasattr(manager.playbook_runner, "list_active_executions")
                    else []
                )
                if execution_id not in active_executions:
                    manager.tasks_store.update_task_status(
                        task_id=task.id,
                        status=TaskStatus.FAILED,
                        error="Execution completed but no result available",
                        completed_at=utc_now(),
                    )

                    error_timeline_item = create_failed_execution_timeline_item(
                        task=task,
                        playbook_code=playbook_code,
                        error_message="Execution completed but no result available",
                        utc_now_fn=utc_now,
                    )
                    manager.timeline_items_store.create_timeline_item(
                        error_timeline_item
                    )

                    logger.warning(
                        "Task %s execution %s no longer active, marked as failed, created error timeline item",
                        task.id,
                        execution_id,
                    )
                else:
                    logger.debug(
                        "Task %s execution %s still in progress",
                        task.id,
                        execution_id,
                    )
        except Exception as exc:
            logger.warning("Failed to check execution status for task %s: %s", task.id, exc)
    except Exception as exc:
        logger.error("Failed to check and update task status: %s", exc, exc_info=True)


async def _get_execution_result_data(
    *,
    manager: Any,
    task: Any,
    execution_id: str,
) -> Optional[dict]:
    execution_result_data = None

    if hasattr(manager.playbook_runner, "get_playbook_execution_result"):
        try:
            execution_result_data = await manager.playbook_runner.get_playbook_execution_result(
                execution_id
            )
        except Exception as exc:
            logger.warning(
                "Failed to get execution result for %s: %s, falling back to active executions check",
                execution_id,
                exc,
            )
    else:
        logger.warning(
            "playbook_runner.get_playbook_execution_result not available, checking active executions"
        )

    if execution_result_data is not None:
        return execution_result_data

    if hasattr(manager.playbook_runner, "list_active_executions"):
        try:
            active_executions = manager.playbook_runner.list_active_executions()
            if execution_id in active_executions:
                return None

            if task.result:
                logger.info("Using task.result for completed execution %s", execution_id)
                return task.result if isinstance(task.result, dict) else {
                    "result": task.result,
                    "status": "completed",
                }

            logger.warning(
                "Execution %s completed but no result available, creating placeholder TimelineItem",
                execution_id,
            )
            return {
                "status": "completed",
                "note": "Execution completed but result retrieval not available",
            }
        except Exception as exc:
            logger.warning(
                "Failed to check active executions: %s, task %s remains RUNNING",
                exc,
                task.id,
            )
            return None

    logger.warning(
        "playbook_runner.list_active_executions not available, cannot determine execution status for %s",
        execution_id,
    )
    if task.result:
        logger.info("Using task.result as fallback for execution %s", execution_id)
        return task.result if isinstance(task.result, dict) else {
            "result": task.result,
            "status": "completed",
        }

    logger.warning(
        "Cannot determine execution status for %s, task %s remains RUNNING",
        execution_id,
        task.id,
    )
    return None
