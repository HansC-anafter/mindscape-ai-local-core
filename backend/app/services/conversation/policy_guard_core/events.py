"""Event recording for policy checks."""

import logging
import uuid
from typing import Any, Optional

from backend.app.models.mindscape import EventActor, EventType, MindEvent
from backend.app.services.conversation.policy_guard_core.clock import utc_now
from backend.app.services.conversation.policy_guard_core.models import PolicyCheckResult

logger = logging.getLogger(__name__)


def record_policy_check_event(
    *,
    tool_id: str,
    capability_code: Optional[str],
    risk_class: Optional[str],
    result: PolicyCheckResult,
    execution_id: Optional[str],
    workspace_id: Optional[str],
    profile_id: Optional[str],
    event_store: Optional[Any],
):
    """Record a policy check event when event recording is configured."""
    if not event_store or not execution_id:
        return

    try:
        event = MindEvent(
            id=str(uuid.uuid4()),
            timestamp=utc_now(),
            actor=EventActor.SYSTEM,
            channel="runtime_profile",
            profile_id=profile_id or "system",
            workspace_id=workspace_id,
            event_type=EventType.POLICY_CHECK,
            payload={
                "execution_id": execution_id,
                "tool_id": tool_id,
                "capability_code": capability_code,
                "risk_class": risk_class,
                "allowed": result.allowed,
                "requires_approval": result.requires_approval,
                "reason": result.reason,
                "user_message": result.user_message,
            },
        )
        event_store.create(event)
        logger.debug(
            "PolicyGuard: Recorded policy check event for tool_id=%s, "
            "execution_id=%s, allowed=%s",
            tool_id,
            execution_id,
            result.allowed,
        )
    except Exception as exc:
        logger.warning("Failed to record policy check event: %s", exc, exc_info=True)
