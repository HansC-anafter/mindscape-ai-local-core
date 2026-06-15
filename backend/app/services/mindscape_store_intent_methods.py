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


class MindscapeStoreIntentMixin:
    def create_intent(self, intent: IntentCard) -> IntentCard:
        """Create a new intent"""
        return self.intents.create_intent(intent)

    def get_intent(self, intent_id: str) -> Optional[IntentCard]:
        """Get intent by ID"""
        return self.intents.get_intent(intent_id)

    def list_intents(
        self,
        profile_id: str,
        status: Optional[IntentStatus] = None,
        priority: Optional[PriorityLevel] = None,
        project_id: Optional[str] = None,
    ) -> List[IntentCard]:
        """List intents for a profile with optional filters"""
        return self.intents.list_intents(
            profile_id, status=status, priority=priority, project_id=project_id
        )

    def update_intent(self, intent: IntentCard) -> Optional[IntentCard]:
        """Update an existing intent"""
        return self.intents.update_intent(intent)

    def delete_intent(self, intent_id: str) -> bool:
        """Delete an intent by ID"""
        return self.intents.delete_intent(intent_id)
