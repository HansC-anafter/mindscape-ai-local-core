
from backend.app.models.workspace import Artifact, ArtifactType, PrimaryActionType

from .schemas import CreateArtifactRequest
from .state import _utc_now

def create_artifact_from_request(
    request: CreateArtifactRequest, artifact_id: str
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
    primary_action_type = (
        PrimaryActionType.OPEN_EXTERNAL
        if request.external_url
        else PrimaryActionType.DOWNLOAD
    )

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
        created_at=_utc_now(),
        updated_at=_utc_now(),
    )
