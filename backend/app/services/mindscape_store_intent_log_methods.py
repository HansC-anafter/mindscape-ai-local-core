from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.app.models.mindscape import (
    AgentExecution,
    Entity,
    EntityTag,
    EntityType,
    EventActor,
    EventType,
    IntentCard,
    IntentLog,
    IntentStatus,
    MindEvent,
    MindscapeProfile,
    PriorityLevel,
    Tag,
    TagCategory,
)
from backend.app.models.workspace import Workspace
from backend.app.services.mindscape_store_utils import _utc_now


class MindscapeStoreIntentLogMixin:
    def create_intent_log(self, intent_log: IntentLog) -> IntentLog:
        """
        Create a new intent log entry

        Args:
            intent_log: IntentLog to create

        Returns:
            Created IntentLog
        """
        return self.intent_logs.create_intent_log(intent_log)

    def get_intent_log(self, log_id: str) -> Optional[IntentLog]:
        """Get intent log by ID"""
        return self.intent_logs.get_intent_log(log_id)

    def list_intent_logs(
        self,
        profile_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        has_override: Optional[bool] = None,
        limit: int = 100,
    ) -> List[IntentLog]:
        """
        List intent logs with optional filters

        Args:
            profile_id: Optional profile filter
            start_time: Optional start time filter
            end_time: Optional end time filter
            has_override: Optional filter for logs with user override
            limit: Maximum number of logs to return

        Returns:
            List of IntentLog objects, ordered by timestamp DESC
        """
        return self.intent_logs.list_intent_logs(
            profile_id=profile_id,
            start_time=start_time,
            end_time=end_time,
            has_override=has_override,
            limit=limit,
        )

    def update_intent_log_override(
        self, log_id: str, user_override: Dict[str, Any]
    ) -> Optional[IntentLog]:
        """
        Update user override for an intent log

        Args:
            log_id: Log ID
            user_override: User override data

        Returns:
            Updated IntentLog or None if not found
        """
        return self.intent_logs.update_intent_log_override(log_id, user_override)
