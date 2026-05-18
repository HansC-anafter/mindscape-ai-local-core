
from typing import Any, Dict

from backend.app.models.workspace import Artifact, ArtifactType

from .schemas import ArtifactResponse
from .state import _utc_now

def artifact_to_response(
    artifact: Artifact, include_content: bool = False, include_preview: bool = True
) -> ArtifactResponse:
    """Convert Artifact model to API response format

    Args:
        artifact: Artifact model instance
        include_content: Whether to include full content in response
        include_preview: Whether to include content preview (default: True)

    Returns:
        ArtifactResponse with optional content fields
    """

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
    # Priority: actual_file_path (from file write) > file_path (legacy) > storage_ref
    file_path = None
    external_url = None
    if artifact.metadata:
        file_path = artifact.metadata.get("actual_file_path") or artifact.metadata.get(
            "file_path"
        )
        external_url = artifact.metadata.get("external_url")

    # Fallback to storage_ref if not in metadata
    if not file_path and not external_url and artifact.storage_ref:
        if artifact.storage_ref.startswith(
            "http://"
        ) or artifact.storage_ref.startswith("https://"):
            external_url = artifact.storage_ref
        else:
            file_path = artifact.storage_ref

    # Build response metadata including execution_id if available
    response_metadata = (artifact.metadata or {}).copy()
    if artifact.execution_id:
        response_metadata["execution_id"] = artifact.execution_id
        # Also add navigate_to for backward compatibility
        if "navigate_to" not in response_metadata:
            response_metadata["navigate_to"] = artifact.execution_id

    artifact_type_value = (
        artifact.artifact_type.value if artifact.artifact_type else None
    )

    content_preview = None
    if include_preview and artifact.content:
        content_preview = _generate_content_preview(artifact.content)

    content = None
    if include_content:
        content = artifact.content

    platform = None
    if artifact.metadata:
        platform = artifact.metadata.get("platform")

    return ArtifactResponse(
        id=artifact.id,
        workspace_id=artifact.workspace_id,
        intent_id=artifact.intent_id,
        type=api_type,
        title=artifact.title,
        description=artifact.summary,
        file_path=file_path,
        external_url=external_url,
        metadata=response_metadata,
        created_at=(
            artifact.created_at.isoformat()
            if artifact.created_at
            else _utc_now().isoformat()
        ),
        updated_at=(
            artifact.updated_at.isoformat()
            if artifact.updated_at
            else _utc_now().isoformat()
        ),
        task_id=artifact.task_id,
        execution_id=artifact.execution_id,
        thread_id=artifact.thread_id,
        playbook_code=artifact.playbook_code,
        artifact_type=artifact_type_value,
        content=content,
        content_preview=content_preview,
        platform=platform,
    )


def _generate_content_preview(content: Dict[str, Any], max_length: int = 200) -> str:
    """
    Generate content preview text (first 200 characters)

    Args:
        content: Artifact content dictionary
        max_length: Maximum preview length

    Returns:
        Preview text string
    """
    if not content:
        return ""

    # Try to extract main text
    text = ""

    # Case 1: IG posts format
    if "ig_posts" in content and isinstance(content["ig_posts"], list):
        posts = content["ig_posts"]
        if posts:
            text = posts[0].get("text", "")

    # Case 2: Direct text field
    elif "text" in content:
        text = content["text"]

    # Case 3: Direct content field
    elif "content" in content:
        text = str(content["content"])

    # Case 4: Other formats, avoid serializing the full JSON payload.
    # Large artifacts (e.g., account arrays) can be very expensive to dump
    # just to build a short preview.
    else:
        if isinstance(content, dict):
            preferred_keys = [
                "summary",
                "title",
                "message",
                "status",
                "result",
                "output",
            ]
            for key in preferred_keys:
                value = content.get(key)
                if isinstance(value, str) and value.strip():
                    text = value
                    break

            if not text:
                keys = list(content.keys())
                preview_keys = ", ".join(str(k) for k in keys[:5])
                if len(keys) > 5:
                    preview_keys += ", ..."
                text = f"{{{preview_keys}}}"
        else:
            text = str(content)

    # Truncate and add ellipsis
    if len(text) > max_length:
        text = text[:max_length] + "..."

    return text
