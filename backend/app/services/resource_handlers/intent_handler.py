"""
Intent Resource Handler

Implements ResourceHandler interface for Intent resources.
Handles Intent-specific logic like tree building and status filtering.
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from ...models.mindscape import IntentCard, IntentStatus
from ...services.mindscape_store import MindscapeStore
from .base import ResourceHandler

logger = logging.getLogger(__name__)


class IntentResourceHandler(ResourceHandler):
    """Resource handler for Intent resources"""

    def __init__(self, store: Optional[MindscapeStore] = None):
        """Initialize the Intent resource handler"""
        self.store = store or MindscapeStore()

    @property
    def resource_type(self) -> str:
        """Return the resource type identifier"""
        return "intents"

    def _intent_card_to_dict(self, intent_card: IntentCard, workspace_id: str) -> Dict[str, Any]:
        """Convert IntentCard to dictionary"""

        # Map IntentStatus to API status
        status_map = {
            IntentStatus.ACTIVE: "CONFIRMED",
            IntentStatus.COMPLETED: "CONFIRMED",
            IntentStatus.ARCHIVED: "REJECTED",
            IntentStatus.PAUSED: "CANDIDATE",
        }
        api_status = status_map.get(intent_card.status, "CANDIDATE")

        return {
            "id": intent_card.id,
            "workspace_id": workspace_id,
            "title": intent_card.title,
            "description": intent_card.description,
            "status": api_status,
            "parent_id": intent_card.parent_intent_id,
            "metadata": intent_card.metadata or {},
            "created_at": intent_card.created_at.isoformat() if intent_card.created_at else datetime.utcnow().isoformat(),
            "updated_at": intent_card.updated_at.isoformat() if intent_card.updated_at else datetime.utcnow().isoformat(),
        }

    def _build_intent_tree(self, intents: List[IntentCard], workspace_id: str) -> List[Dict[str, Any]]:
        """Build tree structure from flat intent list"""

        # Convert to dictionary format
        intent_dicts = {intent.id: self._intent_card_to_dict(intent, workspace_id) for intent in intents}

        # Create tree nodes
        tree_nodes: Dict[str, Dict[str, Any]] = {}
        root_nodes: List[Dict[str, Any]] = []

        # First pass: create all nodes
        for intent in intents:
            node = {
                **intent_dicts[intent.id],
                "children": []
            }
            tree_nodes[intent.id] = node

        # Second pass: build tree structure
        for intent in intents:
            node = tree_nodes[intent.id]
            if intent.parent_intent_id and intent.parent_intent_id in tree_nodes:
                # Add as child
                parent_node = tree_nodes[intent.parent_intent_id]
                parent_node["children"].append(node)
            else:
                # Root node
                root_nodes.append(node)

        return root_nodes

    async def list(
        self,
        workspace_id: str,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """List all intents for a workspace"""

        filters = filters or {}

        # Get workspace to find owner_user_id (profile_id)
        workspace = self.store.get_workspace(workspace_id)
        if not workspace:
            raise ValueError(f"Workspace {workspace_id} not found")

        profile_id = workspace.owner_user_id

        # Map API status to IntentStatus if provided
        intent_status = None
        if filters.get("status"):
            status_map = {
                "CONFIRMED": IntentStatus.ACTIVE,
                "CANDIDATE": IntentStatus.PAUSED,
                "REJECTED": IntentStatus.ARCHIVED,
            }
            intent_status = status_map.get(filters["status"].upper())

        # Get intents
        intents = self.store.list_intents(
            profile_id=profile_id,
            status=intent_status,
            priority=None
        )

        # Filter by workspace_id in metadata if needed
        filtered_intents = []
        for intent in intents:
            intent_workspace_id = intent.metadata.get("workspace_id") if intent.metadata else None
            if intent_workspace_id == workspace_id or not intent_workspace_id:
                filtered_intents.append(intent)

        # Build tree if requested
        if filters.get("tree", False):
            return self._build_intent_tree(filtered_intents, workspace_id)
        else:
            # Return flat list
            return [self._intent_card_to_dict(intent, workspace_id) for intent in filtered_intents]

    async def get(
        self,
        workspace_id: str,
        resource_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get a single intent by ID"""

        intent_card = self.store.get_intent(resource_id)
        if not intent_card:
            return None

        # Get workspace_id from metadata or use provided one
        intent_workspace_id = intent_card.metadata.get("workspace_id") if intent_card.metadata else None
        if not intent_workspace_id:
            intent_workspace_id = workspace_id

        return self._intent_card_to_dict(intent_card, intent_workspace_id)

    async def create(
        self,
        workspace_id: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create a new intent"""

        from ...models.mindscape import PriorityLevel

        # Get workspace
        workspace = self.store.get_workspace(workspace_id)
        if not workspace:
            raise ValueError(f"Workspace {workspace_id} not found")

        profile_id = workspace.owner_user_id

        # Map API status to IntentStatus
        status_map = {
            "CONFIRMED": IntentStatus.ACTIVE,
            "CANDIDATE": IntentStatus.PAUSED,
            "REJECTED": IntentStatus.ARCHIVED,
        }
        api_status = data.get("status", "CONFIRMED")
        intent_status = status_map.get(api_status.upper(), IntentStatus.ACTIVE)

        # Ensure metadata includes workspace_id
        metadata = data.get("metadata", {})
        metadata["workspace_id"] = workspace_id

        # Create IntentCard
        intent_card = IntentCard(
            id=data.get("id") or str(self.store.intents._generate_uuid()),
            profile_id=profile_id,
            title=data["title"],
            description=data.get("description"),
            status=intent_status,
            parent_intent_id=data.get("parent_id"),
            metadata=metadata,
            priority=PriorityLevel.MEDIUM,
        )

        # Save intent
        created_intent = self.store.intents.create_intent(intent_card)

        return self._intent_card_to_dict(created_intent, workspace_id)

    async def update(
        self,
        workspace_id: str,
        resource_id: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update an existing intent"""

        # Get existing intent
        intent_card = self.store.get_intent(resource_id)
        if not intent_card:
            raise ValueError(f"Intent {resource_id} not found")

        # Update fields
        if "title" in data:
            intent_card.title = data["title"]
        if "description" in data:
            intent_card.description = data["description"]
        if "status" in data:
            status_map = {
                "CONFIRMED": IntentStatus.ACTIVE,
                "CANDIDATE": IntentStatus.PAUSED,
                "REJECTED": IntentStatus.ARCHIVED,
            }
            intent_card.status = status_map.get(data["status"].upper(), IntentStatus.ACTIVE)
        if "parent_id" in data:
            intent_card.parent_intent_id = data["parent_id"]
        if "metadata" in data:
            if not intent_card.metadata:
                intent_card.metadata = {}
            intent_card.metadata.update(data["metadata"])
            intent_card.metadata["workspace_id"] = workspace_id

        # Save updated intent
        updated_intent = self.store.intents.update_intent(intent_card)

        return self._intent_card_to_dict(updated_intent, workspace_id)

    async def delete(
        self,
        workspace_id: str,
        resource_id: str
    ) -> bool:
        """Delete an intent"""

        return self.store.intents.delete_intent(resource_id)

    def get_schema(self) -> Dict[str, Any]:
        """Get the schema for Intent resources"""
        return {
            "resource_type": "intents",
            "schema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "workspace_id": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "status": {"type": "string", "enum": ["CANDIDATE", "CONFIRMED", "REJECTED"]},
                    "parent_id": {"type": "string"},
                    "metadata": {"type": "object"},
                    "created_at": {"type": "string"},
                    "updated_at": {"type": "string"}
                },
                "required": ["id", "title"]
            }
        }

