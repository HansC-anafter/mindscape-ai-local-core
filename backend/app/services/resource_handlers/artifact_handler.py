"""
Artifact Resource Handler

Implements ResourceHandler interface for Artifact resources.
Artifacts represent tangible outputs from playbook execution,
such as illustrations, documents, configurations, etc.
"""

import logging
import uuid
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import List, Optional, Dict, Any

from ...models.workspace import Artifact, ArtifactType, PrimaryActionType
from ...services.mindscape_store import MindscapeStore
from .base import ResourceHandler

logger = logging.getLogger(__name__)


class ArtifactResourceHandler(ResourceHandler):
    """Resource handler for Artifact resources"""

    def __init__(self, store: Optional[MindscapeStore] = None):
        """Initialize the Artifact resource handler"""
        self.store = store or MindscapeStore()

    @property
    def resource_type(self) -> str:
        """Return the resource type identifier"""
        return "artifacts"

    def _artifact_to_dict(self, artifact: Artifact) -> Dict[str, Any]:
        """Convert Artifact model to dictionary"""

        # Map ArtifactType to API type
        type_map = {
            ArtifactType.IMAGE: "illustration",
            ArtifactType.VIDEO: "illustration",
            ArtifactType.CANVA: "illustration",
            ArtifactType.DOCX: "document",
            ArtifactType.CODE: "document",
            ArtifactType.DATA: "document",
            ArtifactType.LINK: "document",
            ArtifactType.CHECKLIST: "document",
            ArtifactType.DRAFT: "document",
            ArtifactType.CONFIG: "document",
        }

        api_type = type_map.get(artifact.artifact_type, "other")

        # Extract file_path or external_url from storage_ref or metadata
        file_path = artifact.metadata.get("file_path") if artifact.metadata else None
        external_url = (
            artifact.metadata.get("external_url") if artifact.metadata else None
        )

        # Fallback to storage_ref if not in metadata
        if not file_path and not external_url and artifact.storage_ref:
            if artifact.storage_ref.startswith(
                "http://"
            ) or artifact.storage_ref.startswith("https://"):
                external_url = artifact.storage_ref
            else:
                file_path = artifact.storage_ref

        return {
            "id": artifact.id,
            "workspace_id": artifact.workspace_id,
            "intent_id": artifact.intent_id,
            "type": api_type,
            "title": artifact.title,
            "description": artifact.summary,
            "file_path": file_path,
            "external_url": external_url,
            "metadata": artifact.metadata or {},
            "created_at": (
                artifact.created_at.isoformat()
                if artifact.created_at
                else _utc_now().isoformat()
            ),
            "updated_at": (
                artifact.updated_at.isoformat()
                if artifact.updated_at
                else _utc_now().isoformat()
            ),
        }

    def _create_artifact_from_data(
        self, workspace_id: str, data: Dict[str, Any], artifact_id: str
    ) -> Artifact:
        """Create Artifact model from data dictionary"""

        # Map API type to ArtifactType.
        # Note: for draft-like artifacts created from Workbench (e.g., divi_slot_draft),
        # prefer ArtifactType.DRAFT to make it semantically clear in downstream UIs.
        metadata = data.get("metadata", {}).copy()
        kind = (metadata.get("kind") or "").strip().lower()

        if kind.endswith("_draft") or kind in {"divi_slot_draft", "content_draft"}:
            artifact_type = ArtifactType.DRAFT
        else:
            type_map = {
                "illustration": ArtifactType.IMAGE,
                "document": ArtifactType.DOCX,
                "other": ArtifactType.FILE,
            }
            artifact_type = type_map.get(data.get("type", "other"), ArtifactType.FILE)

        # Determine storage_ref from file_path or external_url
        storage_ref = data.get("external_url") or data.get("file_path")

        # Add file_path and external_url to metadata if provided
        if data.get("file_path"):
            metadata["file_path"] = data["file_path"]
        if data.get("external_url"):
            metadata["external_url"] = data["external_url"]

        # Determine primary_action_type based on type
        primary_action_type = (
            PrimaryActionType.OPEN_EXTERNAL
            if data.get("external_url")
            else PrimaryActionType.DOWNLOAD
        )

        return Artifact(
            id=artifact_id,
            workspace_id=workspace_id,
            intent_id=data.get("intent_id"),
            task_id=None,
            execution_id=None,
            thread_id=data.get("thread_id"),
            playbook_code=metadata.get("playbook_code", "manual"),
            artifact_type=artifact_type,
            title=data.get("title", ""),
            summary=data.get("description", ""),
            content=(
                data.get("content", {}) if isinstance(data.get("content"), dict) else {}
            ),
            storage_ref=storage_ref,
            sync_state=None,
            primary_action_type=primary_action_type,
            metadata=metadata,
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )

    async def list(
        self, workspace_id: str, filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """List all artifacts for a workspace"""

        filters = filters or {}

        # Get artifacts from store
        artifacts = self.store.artifacts.list_artifacts_by_workspace(workspace_id)

        # Apply filters
        filtered_artifacts = artifacts

        if filters.get("type"):
            # Map API type to ArtifactType for filtering
            type_filter_map = {
                "illustration": [
                    ArtifactType.IMAGE,
                    ArtifactType.VIDEO,
                    ArtifactType.CANVA,
                ],
                "document": [
                    ArtifactType.DOCX,
                    ArtifactType.CODE,
                    ArtifactType.DATA,
                    ArtifactType.LINK,
                    ArtifactType.CHECKLIST,
                    ArtifactType.DRAFT,
                    ArtifactType.CONFIG,
                ],
            }
            requested_type = filters["type"].lower()
            allowed_types = type_filter_map.get(requested_type, [])
            if allowed_types:
                filtered_artifacts = [
                    a for a in filtered_artifacts if a.artifact_type in allowed_types
                ]

        if filters.get("intent_id"):
            filtered_artifacts = [
                a for a in filtered_artifacts if a.intent_id == filters["intent_id"]
            ]

        # Convert to dictionaries
        return [self._artifact_to_dict(artifact) for artifact in filtered_artifacts]

    async def get(
        self, workspace_id: str, resource_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get a single artifact by ID"""

        artifact = self.store.artifacts.get_artifact(resource_id)
        if not artifact:
            return None

        # Verify it belongs to the workspace
        if artifact.workspace_id != workspace_id:
            return None

        return self._artifact_to_dict(artifact)

    async def create(self, workspace_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new artifact"""

        # Validate workspace exists
        workspace = await self.store.get_workspace(workspace_id)
        if not workspace:
            raise ValueError(f"Workspace {workspace_id} not found")

        # Validate intent exists if provided
        if data.get("intent_id"):
            intent = self.store.get_intent(data["intent_id"])
            if not intent:
                raise ValueError(f"Intent {data['intent_id']} not found")

        # Create artifact ID
        artifact_id = data.get("id") or str(uuid.uuid4())

        # Create Artifact model
        artifact = self._create_artifact_from_data(workspace_id, data, artifact_id)

        # Save to database
        created_artifact = self.store.artifacts.create_artifact(artifact)

        return self._artifact_to_dict(created_artifact)

    async def update(
        self, workspace_id: str, resource_id: str, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update an existing artifact"""

        # Get existing artifact
        artifact = self.store.artifacts.get_artifact(resource_id)
        if not artifact:
            raise ValueError(f"Artifact {resource_id} not found")

        # Verify it belongs to the workspace
        if artifact.workspace_id != workspace_id:
            raise ValueError(
                f"Artifact {resource_id} does not belong to workspace {workspace_id}"
            )

        # Update fields
        if "title" in data:
            artifact.title = data["title"]
        if "description" in data:
            artifact.summary = data["description"]
        if "intent_id" in data:
            artifact.intent_id = data["intent_id"]
        if "type" in data:
            type_map = {
                "illustration": ArtifactType.IMAGE,
                "document": ArtifactType.DOCX,
                "other": ArtifactType.FILE,
            }
            artifact.artifact_type = type_map.get(data["type"], ArtifactType.FILE)
        if "file_path" in data or "external_url" in data:
            storage_ref = data.get("external_url") or data.get("file_path")
            artifact.storage_ref = storage_ref
            if not artifact.metadata:
                artifact.metadata = {}
            if "file_path" in data:
                artifact.metadata["file_path"] = data["file_path"]
            if "external_url" in data:
                artifact.metadata["external_url"] = data["external_url"]
        if "metadata" in data:
            if not artifact.metadata:
                artifact.metadata = {}
            artifact.metadata.update(data["metadata"])

        artifact.updated_at = _utc_now()

        # Save updated artifact
        updated_artifact = self.store.artifacts.update_artifact(artifact)

        return self._artifact_to_dict(updated_artifact)

    async def delete(self, workspace_id: str, resource_id: str) -> bool:
        """Delete an artifact"""

        # Get artifact
        artifact = self.store.artifacts.get_artifact(resource_id)
        if not artifact:
            return False

        # Verify it belongs to the workspace
        if artifact.workspace_id != workspace_id:
            return False

        # Delete artifact
        return self.store.artifacts.delete_artifact(resource_id)

    def get_schema(self) -> Dict[str, Any]:
        """Get the schema for Artifact resources"""
        return {
            "resource_type": "artifacts",
            "schema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "workspace_id": {"type": "string"},
                    "intent_id": {"type": "string"},
                    "type": {
                        "type": "string",
                        "enum": ["illustration", "document", "other"],
                    },
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "file_path": {"type": "string"},
                    "external_url": {"type": "string"},
                    "metadata": {"type": "object"},
                    "created_at": {"type": "string"},
                    "updated_at": {"type": "string"},
                },
                "required": ["id", "title"],
            },
        }
