import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.app.models.mindscape import (
    EventActor,
    EventType,
    IntentCard,
    IntentStatus,
    MindEvent,
    PriorityLevel,
)
from backend.app.models.workspace import TimelineItem, TimelineItemType
from backend.app.services.i18n_service import get_i18n_service
from backend.app.services.stores.postgres.timeline_items_store import (
    PostgresTimelineItemsStore,
)

logger = logging.getLogger(__name__)


def _utc_now():
    return datetime.now(timezone.utc)


def build_empty_action_response(workspace_id: str) -> Dict[str, Any]:
    return {
        "workspace_id": workspace_id,
        "display_events": [],
        "triggered_playbook": None,
        "pending_tasks": [],
    }


def create_user_event(
    *,
    store,
    workspace_id: str,
    profile_id: str,
    project_id: Optional[str],
    message: str,
    action: str,
    action_params: Dict[str, Any],
) -> None:
    user_event = MindEvent(
        id=str(uuid.uuid4()),
        timestamp=_utc_now(),
        actor=EventActor.USER,
        channel="local_workspace",
        profile_id=profile_id,
        project_id=project_id,
        workspace_id=workspace_id,
        event_type=EventType.MESSAGE,
        payload={
            "message": message,
            "action": action,
            "action_params": action_params,
        },
        entity_ids=[],
        metadata={},
    )
    store.create_event(user_event)


def handle_error(
    *,
    store,
    default_locale: str,
    workspace_id: str,
    profile_id: str,
    project_id: Optional[str],
    error_message: str,
) -> Dict[str, Any]:
    i18n = get_i18n_service(default_locale=default_locale)
    error_msg = i18n.t(
        "conversation_orchestrator",
        "error.execute_action_failed",
        error=error_message,
    )

    error_event = MindEvent(
        id=str(uuid.uuid4()),
        timestamp=_utc_now(),
        actor=EventActor.SYSTEM,
        channel="local_workspace",
        profile_id=profile_id,
        project_id=project_id,
        workspace_id=workspace_id,
        event_type=EventType.MESSAGE,
        payload={"message": error_msg},
        entity_ids=[],
        metadata={},
    )
    store.create_event(error_event)
    return build_empty_action_response(workspace_id)


def handle_add_to_mindscape(
    *,
    store,
    default_locale: str,
    ctx,
    action_params: Dict[str, Any],
    message_id: Optional[str],
) -> Dict[str, Any]:
    try:
        intents = action_params.get("intents", [])
        themes = action_params.get("themes", [])
        if not intents:
            raise ValueError("No intents provided in action_params")

        existing_intents = store.list_intents(profile_id=ctx.actor_id)
        existing_titles = {intent.title for intent in existing_intents}

        intents_added = []
        for intent_item in intents[:10]:
            if isinstance(intent_item, str):
                intent_text = intent_item
                intent_title = intent_item
            elif isinstance(intent_item, dict):
                intent_text = (
                    intent_item.get("text")
                    or intent_item.get("title")
                    or intent_item.get("intent", "")
                )
                intent_title = intent_item.get("title") or intent_text
            else:
                continue

            if not intent_text or not intent_text.strip():
                continue

            if intent_text in existing_titles or intent_title in existing_titles:
                continue

            new_intent = IntentCard(
                id=str(uuid.uuid4()),
                profile_id=ctx.actor_id,
                title=intent_title,
                description="Added from suggestion action: add_to_mindscape",
                status=IntentStatus.ACTIVE,
                priority=PriorityLevel.MEDIUM,
                tags=[],
                category="suggestion_action",
                progress_percentage=0,
                created_at=_utc_now(),
                updated_at=_utc_now(),
                started_at=None,
                completed_at=None,
                due_date=None,
                parent_intent_id=None,
                child_intent_ids=[],
                metadata={
                    "source": "suggestion_action",
                    "action": "add_to_mindscape",
                    "workspace_id": ctx.workspace_id,
                },
            )
            store.create_intent(new_intent)
            intents_added.append(intent_title)
            existing_titles.add(intent_title)
            logger.info(
                "Created intent from add_to_mindscape: %s",
                intent_title[:50],
            )

        timeline_item = TimelineItem(
            id=str(uuid.uuid4()),
            workspace_id=ctx.workspace_id,
            message_id=message_id or str(uuid.uuid4()),
            task_id=None,
            type=TimelineItemType.INTENT_SEEDS,
            title=f"Added {len(intents_added)} intent(s) to Mindscape",
            summary=f"Successfully added {len(intents_added)} intent(s) from suggestion",
            data={
                "action": "add_to_mindscape",
                "intents_added": intents_added,
                "themes": themes,
            },
            cta=None,
            created_at=_utc_now(),
        )
        PostgresTimelineItemsStore().create_timeline_item(timeline_item)

        logger.info(
            "INTENT_METRICS: manual_confirmation, action=add_to_mindscape, "
            "workspace_id=%s, profile_id=%s, intents_added=%s, message_id=%s, "
            "timestamp=%s",
            ctx.workspace_id,
            ctx.actor_id,
            len(intents_added),
            message_id,
            _utc_now().isoformat(),
        )

        i18n = get_i18n_service(default_locale=default_locale)
        success_message = (
            i18n.t("conversation_orchestrator", "suggestion.add_to_mindscape")
            + f" Added {len(intents_added)} intent(s)."
        )

        response = build_empty_action_response(ctx.workspace_id)
        response["message"] = success_message
        return response
    except Exception as exc:
        logger.error(
            "Failed to handle add_to_mindscape action: %s",
            exc,
            exc_info=True,
        )
        raise ValueError(f"Failed to add intents to Mindscape: {str(exc)}") from exc


def handle_create_intent(
    *,
    store,
    default_locale: str,
    ctx,
    action_params: Dict[str, Any],
    project_id: Optional[str],
) -> Dict[str, Any]:
    i18n = get_i18n_service(default_locale=default_locale)

    title = action_params.get("title") or action_params.get("intent_title")
    description = action_params.get("description") or action_params.get(
        "intent_description"
    )

    if not title:
        title = i18n.t(
            "conversation_orchestrator",
            "create_intent_card_title",
            default="New Intent",
        )
    if not description:
        description = i18n.t(
            "conversation_orchestrator",
            "create_intent_card_description",
            default="Start tracking your long-term goals and tasks",
        )

    new_intent = IntentCard(
        id=str(uuid.uuid4()),
        profile_id=ctx.actor_id,
        title=title,
        description=description,
        priority=PriorityLevel.MEDIUM,
        status=IntentStatus.ACTIVE,
        tags=action_params.get("tags", []),
        category=action_params.get("category"),
        progress_percentage=0.0,
        created_at=_utc_now(),
        updated_at=_utc_now(),
        started_at=None,
        completed_at=None,
        due_date=None,
        parent_intent_id=None,
        child_intent_ids=[],
        metadata={},
    )

    try:
        created_intent = store.create_intent(new_intent)
        logger.info(
            "_handle_create_intent: Created intent card %s for user %s",
            created_intent.id,
            ctx.actor_id,
        )

        is_high_priority = created_intent.priority in [
            PriorityLevel.HIGH,
            PriorityLevel.CRITICAL,
        ]
        intent_event = MindEvent(
            id=str(uuid.uuid4()),
            timestamp=_utc_now(),
            actor=EventActor.USER,
            channel="local_workspace",
            profile_id=ctx.actor_id,
            project_id=project_id,
            workspace_id=ctx.workspace_id,
            event_type=EventType.INTENT_CREATED,
            payload={
                "intent_id": created_intent.id,
                "title": created_intent.title,
                "description": created_intent.description,
                "status": created_intent.status.value,
                "priority": created_intent.priority.value,
            },
            entity_ids=[created_intent.id],
            metadata={
                "should_embed": is_high_priority,
                "is_artifact": is_high_priority,
            },
        )
        store.create_event(intent_event, generate_embedding=is_high_priority)

        success_message = i18n.t(
            "conversation_orchestrator",
            "intent.created",
            intent_title=created_intent.title,
            default=f"Intent card '{created_intent.title}' created successfully",
        )
        return {
            "workspace_id": ctx.workspace_id,
            "display_events": [
                {
                    "type": "message",
                    "content": success_message,
                    "timestamp": _utc_now().isoformat(),
                }
            ],
            "triggered_playbook": None,
            "pending_tasks": [],
            "created_intent": {
                "id": created_intent.id,
                "title": created_intent.title,
            },
        }
    except Exception as exc:
        logger.error(
            "_handle_create_intent: Failed to create intent: %s",
            exc,
            exc_info=True,
        )
        error_message = i18n.t(
            "conversation_orchestrator",
            "intent.create_failed",
            error=str(exc),
            default=f"Failed to create intent card: {str(exc)}",
        )
        return {
            "workspace_id": ctx.workspace_id,
            "display_events": [
                {
                    "type": "error",
                    "content": error_message,
                    "timestamp": _utc_now().isoformat(),
                }
            ],
            "triggered_playbook": None,
            "pending_tasks": [],
        }
