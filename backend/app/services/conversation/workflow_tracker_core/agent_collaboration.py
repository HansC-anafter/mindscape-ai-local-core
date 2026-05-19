"""Agent collaboration event helpers for WorkflowTracker."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from backend.app.models.mindscape import EventActor, EventType, MindEvent
from backend.app.services.conversation.workflow_tracker_core.clock import utc_now

logger = logging.getLogger(__name__)


def create_agent_collaboration_event(
    *,
    tracker: Any,
    execution_id: str,
    step_id: str,
    participants: List[str],
    topic: str,
    collaboration_type: str = "discussion",
    discussion: Optional[List[Dict[str, str]]] = None,
    workspace_id: Optional[str] = None,
    profile_id: Optional[str] = None,
) -> MindEvent:
    collaboration_event_id = str(uuid.uuid4())
    now = utc_now()

    payload = {
        "execution_id": execution_id,
        "step_id": step_id,
        "collaboration_type": collaboration_type,
        "participants": participants,
        "topic": topic,
        "discussion": discussion or [],
        "status": "active",
        "started_at": now.isoformat(),
    }

    event = MindEvent(
        id=collaboration_event_id,
        timestamp=now,
        actor=EventActor.SYSTEM,
        channel="workspace",
        workspace_id=workspace_id,
        profile_id=profile_id,
        event_type=EventType.AGENT_EXECUTION,
        payload=payload,
        entity_ids=[execution_id] if execution_id else [],
        metadata={
            "is_agent_collaboration": True,
            "collaboration_type": collaboration_type,
        },
    )

    try:
        tracker.store.create_event(event)
        logger.debug(
            "Created AGENT_EXECUTION event: %s for collaboration: %s",
            collaboration_event_id,
            topic,
        )
    except Exception as exc:
        logger.warning("Failed to create AGENT_EXECUTION event: %s", exc)

    return event


def update_agent_collaboration_event(
    *,
    tracker: Any,
    collaboration_event_id: str,
    status: str = "completed",
    discussion: Optional[List[Dict[str, str]]] = None,
    result: Optional[Dict[str, Any]] = None,
) -> bool:
    try:
        event = tracker.store.get_event(collaboration_event_id)
        if not event or event.event_type != EventType.AGENT_EXECUTION:
            logger.warning(
                "Event %s not found or not an AGENT_EXECUTION event",
                collaboration_event_id,
            )
            return False

        payload = event.payload or {}
        payload["status"] = status
        if discussion:
            existing_discussion = payload.get("discussion", [])
            payload["discussion"] = existing_discussion + discussion
        if result:
            payload["result"] = result
        if status == "completed":
            payload["completed_at"] = utc_now().isoformat()

        event.payload = payload
        tracker.store.update_event(event)
        return True
    except Exception as exc:
        logger.warning("Failed to update AGENT_EXECUTION event: %s", exc)
        return False
