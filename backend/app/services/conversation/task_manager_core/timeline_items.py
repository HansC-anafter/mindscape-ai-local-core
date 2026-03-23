"""Timeline item shaping helpers extracted from TaskManager."""

from __future__ import annotations

import uuid
from typing import Any, Callable, Dict, List

from backend.app.models.workspace import (
    SideEffectLevel,
    TimelineItem,
    TimelineItemType,
)


def resolve_timeline_item_type(
    playbook_code: str,
    execution_result: Dict[str, Any],
) -> TimelineItemType:
    """Infer the timeline item type from the playbook and result payload."""
    playbook_lower = playbook_code.lower()
    if execution_result.get("error") or "error" in playbook_lower:
        return TimelineItemType.ERROR
    if (
        "semantic_seeds" in playbook_lower
        or "intent" in playbook_lower
        or "seed" in playbook_lower
    ):
        return TimelineItemType.INTENT_SEEDS
    if "draft" in playbook_lower or "content_drafting" in playbook_lower:
        return TimelineItemType.DRAFT
    if "summary" in playbook_lower or "summarize" in playbook_lower:
        return TimelineItemType.SUMMARY

    result_type = execution_result.get("type")
    if result_type:
        try:
            return TimelineItemType(result_type)
        except (TypeError, ValueError):
            pass

    return TimelineItemType.PLAN


def resolve_view_result_label(playbook_code: str) -> str:
    """Return the CTA label that matches the playbook domain."""
    playbook_lower = playbook_code.lower()
    if (
        "draft" in playbook_lower
        or "content" in playbook_lower
        or "writing" in playbook_lower
    ):
        return "View File"
    if "plan" in playbook_lower or "planning" in playbook_lower:
        return "View Plan"
    if "summary" in playbook_lower or "summarize" in playbook_lower:
        return "View Summary"
    if "intent" in playbook_lower or "seed" in playbook_lower:
        return "View Intent"
    if "task" in playbook_lower:
        return "View Task"
    return "View Result"


def build_timeline_cta(
    *,
    playbook_code: str,
    execution_result: Dict[str, Any],
    side_effect_level: SideEffectLevel,
    i18n: Any,
) -> List[Dict[str, Any]]:
    """Build the CTA payload without touching stores."""
    view_result_label = resolve_view_result_label(playbook_code)
    playbook_lower = playbook_code.lower()

    if side_effect_level == SideEffectLevel.SOFT_WRITE:
        action_type = execution_result.get("action_type") or "add_to_intents"
        if "intent" in playbook_lower or "seed" in playbook_lower:
            action_type = "add_to_intents"
        elif "task" in playbook_lower or "plan" in playbook_lower:
            action_type = "add_to_tasks"
        return [
            {
                "label": i18n.t("conversation_orchestrator", "suggestion.cta_add"),
                "action": action_type,
            },
            {"label": view_result_label, "action": "view_result"},
        ]

    if side_effect_level == SideEffectLevel.EXTERNAL_WRITE:
        action_type = execution_result.get("action_type") or "publish_to_wordpress"
        if "wordpress" in playbook_lower or "wp" in playbook_lower:
            action_type = "publish_to_wordpress"
        elif "export" in playbook_lower:
            action_type = "export_document"
        else:
            action_type = "execute_external_action"

        return [
            {
                "label": i18n.t(
                    "conversation_orchestrator",
                    "confirmation.button_confirm",
                ),
                "action": action_type,
                "requires_confirm": True,
            },
            {"label": view_result_label, "action": "view_result"},
        ]

    return [{"label": view_result_label, "action": "view_result"}]


def create_task_completion_timeline_item(
    *,
    task: Any,
    execution_result: Dict[str, Any],
    playbook_code: str,
    side_effect_level: SideEffectLevel,
    i18n: Any,
    utc_now_fn: Callable[[], Any],
) -> TimelineItem:
    """Create the success timeline item for a completed task."""
    return TimelineItem(
        id=str(uuid.uuid4()),
        workspace_id=task.workspace_id,
        message_id=task.message_id,
        task_id=task.id,
        type=resolve_timeline_item_type(playbook_code, execution_result),
        title=execution_result.get("title") or playbook_code,
        summary=(
            execution_result.get("summary")
            or execution_result.get("message")
            or f"Completed {playbook_code}"
        ),
        data=execution_result,
        cta=build_timeline_cta(
            playbook_code=playbook_code,
            execution_result=execution_result,
            side_effect_level=side_effect_level,
            i18n=i18n,
        ),
        created_at=utc_now_fn(),
    )


def create_failed_execution_timeline_item(
    *,
    task: Any,
    playbook_code: str,
    error_message: str,
    utc_now_fn: Callable[[], Any],
) -> TimelineItem:
    """Create the fallback error item when async execution has no result."""
    return TimelineItem(
        id=str(uuid.uuid4()),
        workspace_id=task.workspace_id,
        message_id=task.message_id,
        task_id=task.id,
        type=TimelineItemType.ERROR,
        title=f"Failed: {playbook_code}",
        summary=error_message,
        data={
            "playbook_code": playbook_code,
            "error": error_message,
        },
        cta=None,
        created_at=utc_now_fn(),
    )


def create_timeout_timeline_item(
    *,
    task: Any,
    timeout_error: str,
    timeout_minutes: int,
    i18n: Any,
    utc_now_fn: Callable[[], Any],
) -> TimelineItem:
    """Create the error item recorded when a task times out."""
    return TimelineItem(
        id=str(uuid.uuid4()),
        workspace_id=task.workspace_id,
        message_id=task.message_id,
        task_id=task.id,
        type=TimelineItemType.ERROR,
        title=i18n.t(
            "conversation_orchestrator",
            "timeline.task_timeout_title",
            default="Task Timed Out",
        ),
        summary=i18n.t(
            "conversation_orchestrator",
            "timeline.task_timeout_summary",
            timeout_minutes=timeout_minutes,
            default=f"Task timed out after {timeout_minutes} minutes",
        ),
        data={
            "error": timeout_error,
            "task_id": task.id,
            "pack_id": task.pack_id,
            "timeout_minutes": timeout_minutes,
        },
        cta=None,
        created_at=utc_now_fn(),
    )
