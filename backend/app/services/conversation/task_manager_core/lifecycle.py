"""Task lifecycle helpers behind the TaskManager facade."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from backend.app.models.workspace import TaskStatus, TimelineItem
from backend.app.services.conversation.task_manager_core.artifacts import (
    attach_artifact_to_timeline_item,
)
from backend.app.services.conversation.task_manager_core.timeline_items import (
    create_task_completion_timeline_item,
)
from backend.app.services.execution_core.clock import utc_now

logger = logging.getLogger(__name__)


async def create_timeline_item_from_task(
    *,
    manager: Any,
    task: Any,
    execution_result: Dict[str, Any],
    playbook_code: str,
) -> Optional[TimelineItem]:
    """Create a timeline item from a completed task through TaskManager stores."""
    try:
        side_effect_level = manager.plan_builder.determine_side_effect_level(
            playbook_code
        )
        timeline_item = create_task_completion_timeline_item(
            task=task,
            execution_result=execution_result,
            playbook_code=playbook_code,
            side_effect_level=side_effect_level,
            i18n=manager.i18n,
            utc_now_fn=utc_now,
        )

        manager.timeline_items_store.create_timeline_item(timeline_item)
        logger.info("Created timeline item: %s for task %s", timeline_item.id, task.id)

        if manager.artifacts_store:
            await attach_artifact_to_timeline_item(
                store=manager.store,
                artifacts_store=manager.artifacts_store,
                timeline_items_store=manager.timeline_items_store,
                artifact_extractor=manager.artifact_extractor,
                task=task,
                timeline_item=timeline_item,
                execution_result=execution_result,
                playbook_code=playbook_code,
                get_next_version_fn=manager.artifact_extractor._get_next_version,
                update_latest_markers_fn=manager._update_artifact_latest_markers,
                create_mind_event_fn=manager._create_artifact_mind_event,
            )

        manager.tasks_store.update_task_status(
            task_id=task.id,
            status=TaskStatus.SUCCEEDED,
            result=execution_result,
            completed_at=utc_now(),
        )

        await manager._create_graph_node_for_task(
            task=task,
            timeline_item=timeline_item,
            playbook_code=playbook_code,
            execution_result=execution_result,
        )

        mark_task_notification_sent(manager=manager, task_id=task.id)
        return timeline_item
    except Exception as exc:
        logger.error(
            "Failed to create TimelineItem from task %s: %s",
            task.id,
            exc,
            exc_info=True,
        )
        try:
            manager.tasks_store.update_task_status(
                task_id=task.id,
                status=TaskStatus.FAILED,
                error=str(exc),
                completed_at=utc_now(),
            )
        except Exception as update_error:
            logger.error("Failed to update task status: %s", update_error)
        return None


def mark_task_notification_sent(*, manager: Any, task_id: str) -> None:
    """Mark a task as ready for completion notification handling."""
    try:
        manager.tasks_store.update_task(task_id, notification_sent_at=utc_now())
        logger.debug("Marked task %s as notification sent", task_id)
    except Exception as exc:
        logger.warning("Failed to mark task %s as notification sent: %s", task_id, exc)


def mark_task_as_displayed(*, manager: Any, task_id: str) -> None:
    """Mark a task completion notification as displayed by the frontend."""
    try:
        manager.tasks_store.update_task(task_id, displayed_at=utc_now())
        logger.debug("Marked task %s as displayed", task_id)
    except Exception as exc:
        logger.warning("Failed to mark task %s as displayed: %s", task_id, exc)
