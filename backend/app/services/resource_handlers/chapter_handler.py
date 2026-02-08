"""
Chapter Resource Handler

Implements ResourceHandler interface for Chapter resources.
Chapters are derived from Intent metadata (chapter field),
grouping related intents by chapter identifier.
"""

import logging
from typing import List, Optional, Dict, Any
from collections import defaultdict

from ...models.mindscape import IntentCard
from ...services.mindscape_store import MindscapeStore
from .base import ResourceHandler

logger = logging.getLogger(__name__)


class ChapterResourceHandler(ResourceHandler):
    """Resource handler for Chapter resources"""

    def __init__(self, store: Optional[MindscapeStore] = None):
        """Initialize the Chapter resource handler"""
        self.store = store or MindscapeStore()

    @property
    def resource_type(self) -> str:
        """Return the resource type identifier"""
        return "chapters"

    def _derive_chapters_from_intents(
        self, intents: List[IntentCard], workspace_id: str
    ) -> List[Dict[str, Any]]:
        """Derive chapters from Intent structure"""

        # Group intents by chapter
        chapter_groups: Dict[str, List[IntentCard]] = defaultdict(list)

        for intent in intents:
            chapter_id = intent.metadata.get("chapter") if intent.metadata else None
            if chapter_id:
                chapter_groups[chapter_id].append(intent)

        # Build chapter dictionaries
        chapters = []
        for chapter_id, chapter_intents in chapter_groups.items():
            # Find the primary intent (usually the one without parent or the first one)
            primary_intent = next(
                (i for i in chapter_intents if not i.parent_intent_id),
                chapter_intents[0] if chapter_intents else None,
            )

            if not primary_intent:
                continue

            # Extract illustration needs from intents
            illustration_needs: List[Dict[str, Any]] = []

            for intent in chapter_intents:
                # Check if intent has illustration needs in metadata
                needs = (
                    intent.metadata.get("illustration_needs")
                    if intent.metadata
                    else None
                )
                if needs and isinstance(needs, list):
                    for need in needs:
                        illustration_needs.append(
                            {
                                "intent_id": intent.id,
                                "type": need.get("type", "diagram"),
                                "description": need.get("description", ""),
                                "style": need.get("style"),
                                "status": need.get("status", "pending"),
                                "artifact_id": need.get("artifact_id"),
                            }
                        )

            # Build chapter dictionary
            chapter = {
                "id": chapter_id,
                "workspace_id": workspace_id,
                "title": primary_intent.title,
                "description": primary_intent.description,
                "parent_intent_id": primary_intent.id,
                "illustration_needs": illustration_needs,
            }
            chapters.append(chapter)

        return chapters

    async def list(
        self, workspace_id: str, filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """List all chapters for a workspace"""

        filters = filters or {}

        # Get workspace to find owner_user_id (profile_id)
        workspace = await self.store.get_workspace(workspace_id)
        if not workspace:
            raise ValueError(f"Workspace {workspace_id} not found")

        profile_id = workspace.owner_user_id

        # Get all intents for this profile
        intents = self.store.list_intents(
            profile_id=profile_id, status=None, priority=None
        )

        # Filter intents that belong to this workspace
        workspace_intents = []
        for intent in intents:
            intent_workspace_id = (
                intent.metadata.get("workspace_id") if intent.metadata else None
            )
            if intent_workspace_id == workspace_id or not intent_workspace_id:
                workspace_intents.append(intent)

        # Derive chapters from intents
        chapters = self._derive_chapters_from_intents(workspace_intents, workspace_id)

        return chapters

    async def get(
        self, workspace_id: str, resource_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get a single chapter by ID"""

        # Get all chapters
        chapters = await self.list(workspace_id)

        # Find the requested chapter
        for chapter in chapters:
            if chapter["id"] == resource_id:
                return chapter

        return None

    async def create(self, workspace_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new chapter

        Note: Chapters are derived from Intent metadata, so creating a chapter
        actually means creating an intent with chapter metadata.
        """

        from ...models.mindscape import IntentCard, IntentStatus, PriorityLevel

        # Get workspace
        workspace = await self.store.get_workspace(workspace_id)
        if not workspace:
            raise ValueError(f"Workspace {workspace_id} not found")

        profile_id = workspace.owner_user_id

        # Ensure metadata includes chapter
        metadata = data.get("metadata", {})
        metadata["workspace_id"] = workspace_id
        metadata["chapter"] = data.get("id") or data.get("chapter_id")

        # Create IntentCard for the chapter
        intent_card = IntentCard(
            id=data.get("intent_id") or str(self.store.intents._generate_uuid()),
            profile_id=profile_id,
            title=data.get("title", ""),
            description=data.get("description"),
            status=IntentStatus.ACTIVE,
            parent_intent_id=data.get("parent_intent_id"),
            metadata=metadata,
            priority=PriorityLevel.MEDIUM,
        )

        # Save intent
        created_intent = self.store.intents.create_intent(intent_card)

        # Return chapter representation
        chapters = await self.list(workspace_id)
        for chapter in chapters:
            if chapter["id"] == metadata["chapter"]:
                return chapter

        raise ValueError("Failed to create chapter")

    async def update(
        self, workspace_id: str, resource_id: str, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update a chapter

        Note: This updates the primary intent for the chapter.
        """

        # Get existing chapter
        chapter = await self.get(workspace_id, resource_id)
        if not chapter:
            raise ValueError(f"Chapter {resource_id} not found")

        # Update the primary intent
        primary_intent_id = chapter.get("parent_intent_id")
        if primary_intent_id:
            intent_card = self.store.get_intent(primary_intent_id)
            if intent_card:
                if "title" in data:
                    intent_card.title = data["title"]
                if "description" in data:
                    intent_card.description = data["description"]

                # Update metadata
                if not intent_card.metadata:
                    intent_card.metadata = {}
                if "metadata" in data:
                    intent_card.metadata.update(data["metadata"])

                # Save updated intent
                self.store.intents.update_intent(intent_card)

        # Return updated chapter
        return await self.get(workspace_id, resource_id)

    async def delete(self, workspace_id: str, resource_id: str) -> bool:
        """
        Delete a chapter

        Note: This deletes all intents associated with the chapter.
        """

        # Get all intents for this workspace
        workspace = await self.store.get_workspace(workspace_id)
        if not workspace:
            return False

        profile_id = workspace.owner_user_id
        intents = self.store.list_intents(profile_id=profile_id)

        # Find and delete intents with this chapter ID
        deleted_count = 0
        for intent in intents:
            intent_workspace_id = (
                intent.metadata.get("workspace_id") if intent.metadata else None
            )
            intent_chapter = intent.metadata.get("chapter") if intent.metadata else None

            if (
                intent_workspace_id == workspace_id or not intent_workspace_id
            ) and intent_chapter == resource_id:
                if self.store.intents.delete_intent(intent.id):
                    deleted_count += 1

        return deleted_count > 0

    def get_schema(self) -> Dict[str, Any]:
        """Get the schema for Chapter resources"""
        return {
            "resource_type": "chapters",
            "schema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "workspace_id": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "parent_intent_id": {"type": "string"},
                    "illustration_needs": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "intent_id": {"type": "string"},
                                "type": {"type": "string"},
                                "description": {"type": "string"},
                                "style": {"type": "string"},
                                "status": {"type": "string"},
                                "artifact_id": {"type": "string"},
                            },
                        },
                    },
                },
                "required": ["id", "title"],
            },
        }
