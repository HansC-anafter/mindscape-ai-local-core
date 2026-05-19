"""Playbook step event helpers for WorkflowTracker."""

from __future__ import annotations

import logging
import uuid
from typing import Any, List, Optional

from backend.app.models.mindscape import EventActor, EventType, MindEvent
from backend.app.services.conversation.workflow_tracker_core.clock import utc_now

logger = logging.getLogger(__name__)


def create_playbook_step_event(
    *,
    tracker: Any,
    execution_id: str,
    step_index: int,
    step_name: str,
    status: str = "running",
    step_type: str = "agent_action",
    agent_type: Optional[str] = None,
    used_tools: Optional[List[str]] = None,
    description: Optional[str] = None,
    log_summary: Optional[str] = None,
    assigned_agent: Optional[str] = None,
    collaborating_agents: Optional[List[str]] = None,
    requires_confirmation: bool = False,
    confirmation_prompt: Optional[str] = None,
    workspace_id: Optional[str] = None,
    profile_id: Optional[str] = None,
    playbook_code: Optional[str] = None,
) -> MindEvent:
    step_event_id = str(uuid.uuid4())
    now = utc_now()

    payload = {
        "execution_id": execution_id,
        "step_index": step_index,
        "step_name": step_name,
        "status": status,
        "step_type": step_type,
        "agent_type": agent_type,
        "used_tools": used_tools or [],
        "description": description,
        "log_summary": log_summary,
        "assigned_agent": assigned_agent,
        "collaborating_agents": collaborating_agents or [],
        "requires_confirmation": requires_confirmation,
        "confirmation_prompt": confirmation_prompt,
        "confirmation_status": "pending" if requires_confirmation else None,
        "started_at": now.isoformat() if status in ["running", "completed"] else None,
        "completed_at": now.isoformat() if status == "completed" else None,
        "playbook_code": playbook_code,
    }

    event = MindEvent(
        id=step_event_id,
        timestamp=now,
        actor=EventActor.SYSTEM,
        channel="workspace",
        workspace_id=workspace_id,
        profile_id=profile_id,
        event_type=EventType.PLAYBOOK_STEP,
        payload=payload,
        entity_ids=[execution_id] if execution_id else [],
        metadata={
            "is_playbook_step": True,
            "playbook_code": playbook_code,
        },
    )

    try:
        tracker.store.create_event(event)
        logger.debug(
            "Created PLAYBOOK_STEP event: %s for execution %s, step %s",
            step_event_id,
            execution_id,
            step_index,
        )
    except Exception as exc:
        logger.warning("Failed to create PLAYBOOK_STEP event: %s", exc)

    return event


def update_playbook_step_event(
    *,
    tracker: Any,
    step_event_id: str,
    status: Optional[str] = None,
    log_summary: Optional[str] = None,
    completed: bool = False,
    error: Optional[str] = None,
) -> bool:
    try:
        event = tracker.store.get_event(step_event_id)
        if not event or event.event_type != EventType.PLAYBOOK_STEP:
            logger.warning(
                "Event %s not found or not a PLAYBOOK_STEP event",
                step_event_id,
            )
            return False

        payload = event.payload or {}
        if status:
            payload["status"] = status
        if log_summary:
            payload["log_summary"] = log_summary
        if error:
            payload["error"] = error
            payload["status"] = "failed"
        if completed:
            payload["status"] = "completed"
            payload["completed_at"] = utc_now().isoformat()

        event.payload = payload
        tracker.store.update_event(event)
        return True
    except Exception as exc:
        logger.warning("Failed to update PLAYBOOK_STEP event: %s", exc)
        return False
