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


class MindscapeStoreProfileMixin:
    def create_profile(self, profile: MindscapeProfile) -> MindscapeProfile:
        """Create a new profile"""
        return self.profiles.create_profile(profile)

    def get_profile(
        self, profile_id: str, apply_habits: bool = True
    ) -> Optional[MindscapeProfile]:
        """
        Get profile by ID

        Args:
            profile_id: Profile ID
            apply_habits: If True, apply confirmed habits to preferences (default: True)
        """
        return self.profiles.get_profile(profile_id, apply_habits=apply_habits)

    def update_profile(
        self, profile_id: str, updates: Dict[str, Any]
    ) -> Optional[MindscapeProfile]:
        """Update profile"""
        return self.profiles.update_profile(profile_id, updates)
