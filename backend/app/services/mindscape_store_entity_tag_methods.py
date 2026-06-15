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


class MindscapeStoreEntityTagMixin:
    def create_entity(self, entity: Entity) -> Entity:
        """Create a new entity"""
        return self.entities.create_entity(entity)

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Get entity by ID"""
        return self.entities.get_entity(entity_id)

    def list_entities(
        self,
        profile_id: Optional[str] = None,
        entity_type: Optional[EntityType] = None,
        limit: int = 100,
    ) -> List[Entity]:
        """List entities with optional filters"""
        return self.entities.list_entities(
            profile_id=profile_id, entity_type=entity_type, limit=limit
        )

    def update_entity(
        self, entity_id: str, updates: Dict[str, Any]
    ) -> Optional[Entity]:
        """Update entity fields"""
        return self.entities.update_entity(entity_id, updates)

    # ==================== Tag Methods (Delegated) ====================

    def create_tag(self, tag: Tag) -> Tag:
        """Create a new tag"""
        return self.entities.create_tag(tag)

    def get_tag(self, tag_id: str) -> Optional[Tag]:
        """Get tag by ID"""
        return self.entities.get_tag(tag_id)

    def list_tags(
        self,
        profile_id: Optional[str] = None,
        category: Optional[TagCategory] = None,
        limit: int = 100,
    ) -> List[Tag]:
        """List tags with optional filters"""
        return self.entities.list_tags(
            profile_id=profile_id, category=category, limit=limit
        )

    # ==================== Entity-Tag Association Methods (Delegated) ====================

    def tag_entity(
        self, entity_id: str, tag_id: str, value: Optional[str] = None
    ) -> EntityTag:
        """Tag an entity with a tag"""
        return self.entities.tag_entity(entity_id, tag_id, value)

    def untag_entity(self, entity_id: str, tag_id: str) -> bool:
        """Remove a tag from an entity"""
        return self.entities.untag_entity(entity_id, tag_id)

    def get_tags_by_entity(self, entity_id: str) -> List[Tag]:
        """Get all tags associated with an entity"""
        return self.entities.get_tags_by_entity(entity_id)

    def get_entities_by_tag(self, tag_id: str, limit: int = 100) -> List[Entity]:
        """Get all entities tagged with a specific tag"""
        return self.entities.get_entities_by_tag(tag_id, limit=limit)

    def get_entities_by_tags(
        self, tag_ids: List[str], profile_id: Optional[str] = None, limit: int = 100
    ) -> List[Entity]:
        """Get entities that have all specified tags (AND logic)"""
        return self.entities.get_entities_by_tags(
            tag_ids, profile_id=profile_id, limit=limit
        )
