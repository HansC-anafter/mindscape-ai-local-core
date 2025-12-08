"""
Artifact API routes
RESTful API for managing artifacts (playbook outputs)

Artifacts represent tangible outputs from playbook execution,
such as illustrations, documents, configurations, etc.
"""

import logging
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Path, Query, Body
from pydantic import BaseModel, Field

from ...models.workspace import Artifact, ArtifactType, PrimaryActionType
from ...services.mindscape_store import MindscapeStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["artifacts"])

# Initialize store (singleton)
store = MindscapeStore()


# ============================================================================
# Request/Response Models
# ============================================================================

class ArtifactResponse(BaseModel):
    """Artifact API response model matching the API draft specification"""
    id: str
    workspace_id: str
    intent_id: Optional[str] = None
    type: str  # 'illustration' | 'document' | 'other'
    title: str
    description: Optional[str] = None
    file_path: Optional[str] = None
    external_url: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class CreateArtifactRequest(BaseModel):
    """Request model for creating a new artifact"""
    workspace_id: str
    intent_id: Optional[str] = None
    type: str  # 'illustration' | 'document' | 'other'
    title: str
    description: Optional[str] = None
    file_path: Optional[str] = None
    external_url: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ListArtifactsResponse(BaseModel):
    """Response model for listing artifacts"""
    artifacts: List[ArtifactResponse]


# ============================================================================
# Helper Functions
# ============================================================================

def artifact_to_response(artifact: Artifact) -> ArtifactResponse:
    """Convert Artifact model to API response format"""

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
    external_url = artifact.metadata.get("external_url") if artifact.metadata else None

    # Fallback to storage_ref if not in metadata
    if not file_path and not external_url and artifact.storage_ref:
        if artifact.storage_ref.startswith("http://") or artifact.storage_ref.startswith("https://"):
            external_url = artifact.storage_ref
        else:
            file_path = artifact.storage_ref

    return ArtifactResponse(
        id=artifact.id,
        workspace_id=artifact.workspace_id,
        intent_id=artifact.intent_id,
        type=api_type,
        title=artifact.title,
        description=artifact.summary,
        file_path=file_path,
        external_url=external_url,
        metadata=artifact.metadata or {},
        created_at=artifact.created_at.isoformat() if artifact.created_at else datetime.utcnow().isoformat(),
        updated_at=artifact.updated_at.isoformat() if artifact.updated_at else datetime.utcnow().isoformat(),
    )


def create_artifact_from_request(
    request: CreateArtifactRequest,
    artifact_id: str
) -> Artifact:
    """Create Artifact model from API request"""

    # Map API type to ArtifactType
    type_map = {
        "illustration": ArtifactType.IMAGE,
        "document": ArtifactType.DOCX,
        "other": ArtifactType.FILE,
    }

    artifact_type = type_map.get(request.type, ArtifactType.FILE)

    # Determine storage_ref from file_path or external_url
    storage_ref = request.external_url or request.file_path

    # Add file_path and external_url to metadata if provided
    metadata = request.metadata.copy() if request.metadata else {}
    if request.file_path:
        metadata["file_path"] = request.file_path
    if request.external_url:
        metadata["external_url"] = request.external_url

    # Determine primary_action_type based on type
    primary_action_type = PrimaryActionType.OPEN_EXTERNAL if request.external_url else PrimaryActionType.DOWNLOAD

    return Artifact(
        id=artifact_id,
        workspace_id=request.workspace_id,
        intent_id=request.intent_id,
        task_id=None,
        execution_id=None,
        playbook_code=request.metadata.get("playbook_code", "manual"),
        artifact_type=artifact_type,
        title=request.title,
        summary=request.description or "",
        content={},
        storage_ref=storage_ref,
        sync_state=None,
        primary_action_type=primary_action_type,
        metadata=metadata,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/workspaces/{workspace_id}/artifacts")
async def list_artifacts(
    workspace_id: str = Path(..., description="Workspace ID"),
    type: Optional[str] = Query(None, description="Filter by type (illustration, document, other)"),
    intent_id: Optional[str] = Query(None, description="Filter by intent ID")
):
    """
    List all artifacts for a workspace

    Supports filtering by type and intent_id
    """
    try:
        # Get artifacts from store
        artifacts = store.artifacts.list_artifacts_by_workspace(workspace_id)

        # Apply filters
        filtered_artifacts = artifacts

        if type:
            # Map API type to ArtifactType for filtering
            type_filter_map = {
                "illustration": [ArtifactType.IMAGE, ArtifactType.VIDEO, ArtifactType.CANVA],
                "document": [ArtifactType.DOCX, ArtifactType.CODE, ArtifactType.DATA, ArtifactType.LINK, ArtifactType.CHECKLIST, ArtifactType.DRAFT, ArtifactType.CONFIG],
            }
            allowed_types = type_filter_map.get(type.lower(), [])
            filtered_artifacts = [
                a for a in filtered_artifacts
                if a.artifact_type in allowed_types
            ]

        if intent_id:
            filtered_artifacts = [
                a for a in filtered_artifacts
                if a.intent_id == intent_id
            ]

        # Convert to response format
        artifact_responses = [artifact_to_response(artifact) for artifact in filtered_artifacts]

        return ListArtifactsResponse(artifacts=artifact_responses)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list artifacts for workspace {workspace_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list artifacts: {str(e)}")


@router.get("/artifacts/{artifact_id}")
async def get_artifact(
    artifact_id: str = Path(..., description="Artifact ID")
):
    """
    Get a single artifact by ID
    """
    try:
        artifact = store.artifacts.get_artifact(artifact_id)
        if not artifact:
            raise HTTPException(status_code=404, detail=f"Artifact {artifact_id} not found")

        return artifact_to_response(artifact)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get artifact {artifact_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get artifact: {str(e)}")


@router.post("/artifacts", status_code=201)
async def create_artifact(
    request: CreateArtifactRequest = Body(...)
):
    """
    Create a new artifact
    """
    try:
        # Validate workspace exists
        workspace = store.get_workspace(request.workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail=f"Workspace {request.workspace_id} not found")

        # Validate intent exists if provided
        if request.intent_id:
            intent = store.get_intent(request.intent_id)
            if not intent:
                raise HTTPException(status_code=404, detail=f"Intent {request.intent_id} not found")

        # Create artifact ID
        artifact_id = str(uuid.uuid4())

        # Create Artifact model
        artifact = create_artifact_from_request(request, artifact_id)

        # Save to database
        created_artifact = store.artifacts.create_artifact(artifact)

        return artifact_to_response(created_artifact)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create artifact: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create artifact: {str(e)}")

