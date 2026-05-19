"""Auto-execution helpers for intent extraction."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from backend.app.models.workspace import TimelineItem, TimelineItemType
from backend.app.services.conversation.intent_extractor_core.clock import utc_now

logger = logging.getLogger(__name__)


def should_auto_execute_intent_extraction(
    auto_exec_config: Optional[Dict[str, Any]],
    confidence: Optional[float],
) -> bool:
    if not auto_exec_config or "intent_extraction" not in auto_exec_config:
        return False

    intent_config = auto_exec_config["intent_extraction"]
    confidence_threshold = intent_config.get("confidence_threshold", 0.8)
    auto_execute_enabled = intent_config.get("auto_execute", False)

    llm_confidence = confidence or 0.0
    if llm_confidence == 0.0:
        llm_confidence = 0.9

    should_execute = bool(
        auto_execute_enabled and llm_confidence >= confidence_threshold
    )
    if should_execute:
        logger.info(
            "IntentExtractor: Intent extraction meets auto-exec threshold "
            "(confidence=%.2f >= %.2f)",
            llm_confidence,
            confidence_threshold,
        )
    else:
        logger.info(
            "IntentExtractor: Intent extraction does not meet auto-exec threshold "
            "(confidence=%.2f < %.2f)",
            llm_confidence,
            confidence_threshold,
        )
    return should_execute


def build_auto_execution_task(
    *,
    ctx: Any,
    message_id: str,
    intents_created: int,
) -> Any:
    from backend.app.models.workspace import Task, TaskStatus

    return Task(
        id=str(uuid.uuid4()),
        workspace_id=ctx.workspace_id,
        message_id=message_id,
        execution_id=None,
        pack_id="system",
        task_type="auto_intent_extraction",
        status=TaskStatus.SUCCEEDED,
        params={
            "action": "create_candidate_intents",
            "candidate_intents_created": intents_created,
            "auto_executed": True,
            "note": (
                "Candidate intents created as IntentTags. Only confirmed intents "
                "will be written to long-term memory."
            ),
        },
        result={
            "action": "create_candidate_intents",
            "candidate_intents_created": intents_created,
        },
        created_at=utc_now(),
        started_at=utc_now(),
        completed_at=utc_now(),
        error=None,
    )


def build_auto_execution_timeline_item(
    *,
    ctx: Any,
    message_id: str,
    action_task_id: str,
    i18n: Any,
    intents_list: List[Any],
    themes_list: List[Any],
    intents_created: int,
    thread_id: Optional[str],
) -> TimelineItem:
    return TimelineItem(
        id=str(uuid.uuid4()),
        workspace_id=ctx.workspace_id,
        message_id=message_id,
        task_id=action_task_id,
        type=TimelineItemType.INTENT_SEEDS,
        title=i18n.t(
            "conversation_orchestrator",
            (
                "timeline.intents_added_title"
                if intents_created > 0
                else "timeline.no_intents_added_title"
            ),
            count=intents_created,
            default=(
                f"Added {intents_created} intent(s) to Mindscape"
                if intents_created > 0
                else "No new intents"
            ),
        ),
        summary=i18n.t(
            "conversation_orchestrator",
            (
                "timeline.intents_added_summary"
                if intents_created > 0
                else "timeline.all_intents_exist_summary"
            ),
            count=intents_created,
            default=(
                f"Auto-added {intents_created} intent(s) from message"
                if intents_created > 0
                else "All intents already exist"
            ),
        ),
        data={
            "intents": intents_list,
            "themes": themes_list,
            "source": "auto_intent_extraction",
            "intents_added": intents_created,
            "auto_executed": True,
            "thread_id": thread_id,
        },
        cta=None,
        created_at=utc_now(),
    )


def create_auto_execution_timeline_item(
    *,
    extractor: Any,
    ctx: Any,
    message_id: str,
    intents_list: List[Any],
    themes_list: List[Any],
    intent_tag_ids: List[str],
    thread_id: Optional[str],
) -> TimelineItem:
    from backend.app.services.stores.tasks_store import TasksStore

    tasks_store = TasksStore()
    intents_created = len(intent_tag_ids)
    action_task = build_auto_execution_task(
        ctx=ctx,
        message_id=message_id,
        intents_created=intents_created,
    )
    tasks_store.create_task(action_task)

    timeline_item = build_auto_execution_timeline_item(
        ctx=ctx,
        message_id=message_id,
        action_task_id=action_task.id,
        i18n=extractor.i18n,
        intents_list=intents_list,
        themes_list=themes_list,
        intents_created=intents_created,
        thread_id=thread_id,
    )

    extractor.timeline_items_store.create_timeline_item(timeline_item)
    logger.info(
        "Intent extractor auto-executed: created timeline item %s with %s intents added",
        timeline_item.id,
        intents_created,
    )
    return timeline_item
