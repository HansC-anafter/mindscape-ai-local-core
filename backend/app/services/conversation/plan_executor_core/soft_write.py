"""Plan executor soft-write handling."""

import logging
from typing import Any, Dict, List, Optional

from backend.app.core.domain_context import LocalDomainContext
from backend.app.services.conversation.task_events_emitter import TaskEventsEmitter

logger = logging.getLogger(__name__)


async def handle_soft_write_task(
    executor,
    task_plan,
    ctx: LocalDomainContext,
    message_id: str,
    files: List[str],
    message: str,
    project_id: Optional[str],
    event_emitter: TaskEventsEmitter,
    auto_exec_config: Optional[Dict[str, Any]],
    execution_priority: str,
    prevent_suggestion_creation: bool,
    suggestion_creator,
) -> Optional[Dict[str, Any]]:
    del executor, files, message, project_id
    if auto_exec_config and task_plan.pack_id in auto_exec_config:
        from backend.app.shared.execution_thresholds import get_threshold

        playbook_config = auto_exec_config[task_plan.pack_id]
        default_threshold = get_threshold(execution_priority)
        confidence_threshold = playbook_config.get(
            "confidence_threshold", default_threshold
        )
        auto_execute_enabled = playbook_config.get("auto_execute", False)
        llm_confidence = (
            task_plan.params.get("llm_analysis", {}).get("confidence", 0.0)
            if task_plan.params
            else 0.0
        )
        if auto_execute_enabled and llm_confidence >= confidence_threshold:
            logger.info(
                f"PlanExecutor: SOFT_WRITE playbook {task_plan.pack_id} meets auto-exec threshold, executing directly"
            )
            playbook_context = task_plan.params.get(
                "context", task_plan.params.copy() if task_plan.params else {}
            )
            if task_plan.params:
                playbook_context.update(task_plan.params)
            return None

    if not prevent_suggestion_creation and suggestion_creator:
        logger.info(
            f"PlanExecutor: Creating suggestion card for SOFT_WRITE task {task_plan.pack_id}"
        )
        suggestion = await suggestion_creator.create_suggestion_card(
            task_plan=task_plan,
            workspace_id=ctx.workspace_id,
            message_id=message_id,
            event_emitter=event_emitter,
        )
        if suggestion:
            logger.info(
                f"PlanExecutor: Suggestion card created for {task_plan.pack_id}"
            )
            return {"suggestion": True, "result": suggestion}

    return None
