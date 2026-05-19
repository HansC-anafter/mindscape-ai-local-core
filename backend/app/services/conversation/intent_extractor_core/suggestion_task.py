"""Suggestion task helpers for intent extraction."""

from __future__ import annotations

import logging
import sys
import uuid
from typing import Any, Dict, List, Optional

from backend.app.services.conversation.intent_extractor_core.clock import utc_now

logger = logging.getLogger(__name__)


def create_suggestion_task(
    *,
    ctx: Any,
    message_id: str,
    intents_list: List[Any],
    themes_list: List[Any],
    llm_analysis: Optional[Dict[str, Any]],
) -> Any:
    from backend.app.models.workspace import Task, TaskStatus
    from backend.app.services.stores.tasks_store import TasksStore

    tasks_store = TasksStore()
    suggestion_task = Task(
        id=str(uuid.uuid4()),
        workspace_id=ctx.workspace_id,
        message_id=message_id,
        execution_id=None,
        pack_id="intent_extraction",
        task_type="suggestion",
        status=TaskStatus.PENDING,
        params={
            "intents": intents_list,
            "themes": themes_list,
            "source": "llm_extractor",
            "requires_cta": True,
        },
        result={
            "suggestion": True,
            "pack_id": "intent_extraction",
            "requires_cta": True,
            "llm_analysis": llm_analysis or {},
        },
        created_at=utc_now(),
        started_at=None,
        completed_at=None,
        error=None,
    )
    tasks_store.create_task(suggestion_task)

    logger.info(
        "Intent extractor created suggestion task %s for workspace %s with %s intents, %s themes",
        suggestion_task.id,
        ctx.workspace_id,
        len(intents_list),
        len(themes_list),
    )
    print(
        f"Intent extractor created suggestion task {suggestion_task.id} "
        f"for workspace {ctx.workspace_id} with {len(intents_list)} intents, {len(themes_list)} themes",
        file=sys.stderr,
    )
    return suggestion_task
