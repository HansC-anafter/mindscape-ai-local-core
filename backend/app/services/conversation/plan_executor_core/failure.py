"""Plan executor failure handling."""

import logging
from typing import Any, Dict

from backend.app.core.domain_context import LocalDomainContext
from backend.app.services.conversation.task_events_emitter import TaskEventsEmitter

logger = logging.getLogger(__name__)


async def handle_execution_failure(
    executor,
    task_plan,
    ctx: LocalDomainContext,
    message_id: str,
    results: Dict[str, Any],
    prevent_suggestion_creation: bool,
    suggestion_creator,
    event_emitter: TaskEventsEmitter,
) -> None:
    pack_id_lower = task_plan.pack_id.lower() if task_plan.pack_id else ""
    if pack_id_lower == "intent_extraction":
        logger.error(
            "PlanExecutor: intent_extraction execution failed in fallback path. "
            "This should not happen - intent_extraction should be handled by IntentInfraService."
        )
        results["skipped_tasks"].append(task_plan.pack_id)
    elif not prevent_suggestion_creation and suggestion_creator:
        pending_tasks = executor.tasks_store.list_pending_tasks(
            ctx.workspace_id, exclude_cancelled=True
        )
        existing_pending = [task for task in pending_tasks if task.pack_id == task_plan.pack_id]
        if existing_pending:
            logger.info(
                f"PlanExecutor: Found existing pending task for {task_plan.pack_id}, skipping suggestion creation"
            )
            results["skipped_tasks"].append(task_plan.pack_id)
        else:
            suggestion = await suggestion_creator.create_suggestion_card(
                task_plan=task_plan,
                workspace_id=ctx.workspace_id,
                message_id=message_id,
                event_emitter=event_emitter,
            )
            if suggestion:
                results["suggestion_cards"].append(suggestion)
