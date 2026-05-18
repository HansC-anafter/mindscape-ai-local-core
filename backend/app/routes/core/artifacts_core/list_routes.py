
import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Path, Query

from backend.app.models.workspace import ArtifactType

from .schemas import ListArtifactsResponse
from .serializers import artifact_to_response
from .state import logger, store

router = APIRouter()

@router.get("/workspaces/{workspace_id}/artifacts")
async def list_artifacts(
    workspace_id: str = Path(..., description="Workspace ID"),
    # Existing parameters (backward compatible)
    type: Optional[str] = Query(
        None, description="Filter by type (illustration, document, other)"
    ),
    intent_id: Optional[str] = Query(None, description="Filter by intent ID"),
    kind: Optional[str] = Query(
        None,
        description="Filter by kind (e.g., 'brand_mi', 'brand_persona', 'brand_storyline')",
    ),
    playbook_code: Optional[str] = Query(
        None, description="Filter by playbook (e.g., 'ig_post_generation')"
    ),
    thread_id: Optional[str] = Query(
        None, description="Filter by conversation thread / meeting session ID"
    ),
    include_content: bool = Query(
        False,
        description="Include full content in response (default: false for performance)",
    ),
    include_preview: bool = Query(
        True, description="Include content preview (default: true)"
    ),
    platform: Optional[str] = Query(
        None, description="Filter by platform (e.g., 'instagram', 'facebook')"
    ),
    limit: int = Query(
        100, description="Maximum number of artifacts to return", ge=1, le=1000
    ),
    offset: int = Query(0, description="Offset for pagination", ge=0),
):
    """
    List all artifacts for a workspace

    Supports filtering by type, intent_id, kind, playbook_code, and platform.
    Supports pagination with limit and offset.

    **Filtering**:
    - `type`: illustration, document, other
    - `playbook_code`: Filter by playbook (e.g., 'ig_post_generation')
    - `platform`: Filter by platform (e.g., 'instagram', 'facebook')
    - `artifact_type`: Internal artifact type

    **Pagination**:
    - `limit`: Maximum number of artifacts (default: 100, max: 1000)
    - `offset`: Offset for pagination (default: 0)

    **Response includes**:
    - `total`: Total number of artifacts matching filters
    - `limit`: Applied limit
    - `offset`: Applied offset
    - `artifacts`: Array of artifact objects

    **Performance**: Response time typically < 200ms for up to 1000 artifacts.
    """
    try:
        # Map API type to internal artifact_type values for DB-side filtering.
        artifact_type_filters = None
        if type:
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
            allowed_types = type_filter_map.get(type.lower(), [])
            artifact_type_filters = [t.value for t in allowed_types]

            # Preserve current behavior: unknown type filter returns empty.
            if not artifact_type_filters:
                return ListArtifactsResponse(
                    artifacts=[], total=0, limit=limit, offset=offset
                )

        needs_content_load = include_content or include_preview

        if thread_id and hasattr(store.artifacts, "get_by_thread"):
            thread_artifacts = await asyncio.to_thread(
                store.artifacts.get_by_thread,
                workspace_id,
                thread_id,
                None,
            )
            filtered_artifacts = thread_artifacts
            if playbook_code:
                filtered_artifacts = [
                    a for a in filtered_artifacts if a.playbook_code == playbook_code
                ]
            if artifact_type_filters is not None:
                allowed = set(artifact_type_filters)
                filtered_artifacts = [
                    a for a in filtered_artifacts if a.artifact_type.value in allowed
                ]
            if intent_id:
                filtered_artifacts = [
                    a for a in filtered_artifacts if a.intent_id == intent_id
                ]
            if kind:
                filtered_artifacts = [
                    a
                    for a in filtered_artifacts
                    if a.metadata and a.metadata.get("kind") == kind
                ]
            if platform:
                filtered_artifacts = [
                    a
                    for a in filtered_artifacts
                    if a.metadata and a.metadata.get("platform") == platform
                ]

            total_count = len(filtered_artifacts)
            paginated_artifacts = filtered_artifacts[offset : offset + limit]
        # Prefer DB-side filtering/pagination to avoid full-table materialization.
        elif hasattr(store.artifacts, "list_artifacts_page") and hasattr(
            store.artifacts, "count_artifacts"
        ):
            total_count = await asyncio.to_thread(
                store.artifacts.count_artifacts,
                workspace_id,
                playbook_code,
                intent_id,
                platform,
                kind,
                artifact_type_filters,
            )
            paginated_artifacts = await asyncio.to_thread(
                store.artifacts.list_artifacts_page,
                workspace_id,
                limit,
                offset,
                playbook_code,
                intent_id,
                platform,
                kind,
                artifact_type_filters,
                needs_content_load,
            )
        else:
            # Backward-compatible fallback for non-Postgres implementations.
            if playbook_code:
                artifacts = await asyncio.to_thread(
                    store.artifacts.list_artifacts_by_playbook,
                    workspace_id,
                    playbook_code,
                )
            else:
                artifacts = await asyncio.to_thread(
                    store.artifacts.list_artifacts_by_workspace, workspace_id
                )

            filtered_artifacts = artifacts
            if artifact_type_filters is not None:
                allowed = set(artifact_type_filters)
                filtered_artifacts = [
                    a for a in filtered_artifacts if a.artifact_type.value in allowed
                ]
            if intent_id:
                filtered_artifacts = [
                    a for a in filtered_artifacts if a.intent_id == intent_id
                ]
            if kind:
                filtered_artifacts = [
                    a
                    for a in filtered_artifacts
                    if a.metadata and a.metadata.get("kind") == kind
                ]
            if platform:
                filtered_artifacts = [
                    a
                    for a in filtered_artifacts
                    if a.metadata and a.metadata.get("platform") == platform
                ]

            total_count = len(filtered_artifacts)
            paginated_artifacts = filtered_artifacts[offset : offset + limit]

        artifact_responses = [
            artifact_to_response(
                artifact,
                include_content=include_content,
                include_preview=include_preview,
            )
            for artifact in paginated_artifacts
        ]

        response = ListArtifactsResponse(
            artifacts=artifact_responses, total=total_count, limit=limit, offset=offset
        )
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to list artifacts for workspace {workspace_id}: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to list artifacts: {str(e)}"
        )
