"""Intent steward input collection."""

import logging

from backend.app.models.mindscape import (
    IntentSignal,
    IntentSource,
    IntentStewardInput,
    IntentTagStatus,
)

logger = logging.getLogger(__name__)


async def collect_input_data(
    service, workspace_id: str, profile_id: str, turn_id: str
) -> IntentStewardInput:
    recent_messages = []
    try:
        events = service.events_store.list_events(
            workspace_id=workspace_id,
            limit=10,
            event_types=["message", "tool_call", "playbook_execution"],
        )
        recent_messages = [
            {
                "id": event.id,
                "type": event.type,
                "content": event.content or "",
                "metadata": event.metadata or {},
                "created_at": event.created_at.isoformat()
                if event.created_at
                else None,
            }
            for event in events
        ]
    except Exception as exc:
        logger.warning(f"Failed to collect recent messages: {exc}")

    recent_signals = []
    try:
        intent_tags = service.intent_tags_store.list_intent_tags(
            workspace_id=workspace_id,
            profile_id=profile_id,
            status=IntentTagStatus.CANDIDATE,
            limit=50,
        )
        for tag in intent_tags:
            signal = IntentSignal(
                id=tag.id,
                workspace_id=tag.workspace_id,
                profile_id=tag.profile_id,
                label=tag.label,
                confidence=tag.confidence or 0.5,
                status=tag.status.value,
                source=(
                    tag.source.value
                    if isinstance(tag.source, IntentSource)
                    else str(tag.source)
                ),
                signal_type="intent",
                message_id=tag.message_id,
                metadata=tag.metadata or {},
                created_at=tag.created_at,
            )
            recent_signals.append(signal)
    except Exception as exc:
        logger.warning(f"Failed to collect recent signals: {exc}")

    current_intent_cards = []
    try:
        all_intents = service.store.list_intents(profile_id=profile_id)
        current_intent_cards = [
            intent
            for intent in all_intents
            if intent.status.value == "active"
            and intent.priority.value in ["high", "medium"]
        ][:10]
    except Exception as exc:
        logger.warning(f"Failed to collect current intent cards: {exc}")

    return IntentStewardInput(
        recent_messages=recent_messages,
        recent_signals=recent_signals,
        current_intent_cards=current_intent_cards,
    )
