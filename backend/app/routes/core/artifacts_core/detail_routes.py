
import asyncio
import uuid

from fastapi import APIRouter, Body, HTTPException, Path, Query

from .creation import create_artifact_from_request
from .schemas import CreateArtifactRequest
from .serializers import artifact_to_response
from .state import logger, store

router = APIRouter()

@router.get("/artifacts/{artifact_id}")
async def get_artifact(
    artifact_id: str = Path(..., description="Artifact ID"),
    include_content: bool = Query(
        False, description="Include full content in response (default: false)"
    ),
    include_preview: bool = Query(
        True, description="Include content preview (default: true)"
    ),
):
    """
    Get a single artifact by ID
    """
    try:
        artifact = await asyncio.to_thread(store.artifacts.get_artifact, artifact_id)
        if not artifact:
            raise HTTPException(
                status_code=404, detail=f"Artifact {artifact_id} not found"
            )

        return artifact_to_response(
            artifact, include_content=include_content, include_preview=include_preview
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get artifact {artifact_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get artifact: {str(e)}")


@router.post("/artifacts", status_code=201)
async def create_artifact(request: CreateArtifactRequest = Body(...)):
    """
    Create a new artifact
    """
    try:
        # Validate workspace exists
        workspace = await store.get_workspace(request.workspace_id)
        if not workspace:
            raise HTTPException(
                status_code=404, detail=f"Workspace {request.workspace_id} not found"
            )

        # Validate intent exists if provided
        if request.intent_id:
            intent = await asyncio.to_thread(store.get_intent, request.intent_id)
            if not intent:
                raise HTTPException(
                    status_code=404, detail=f"Intent {request.intent_id} not found"
                )

        # Create artifact ID
        artifact_id = str(uuid.uuid4())

        # Create Artifact model
        artifact = create_artifact_from_request(request, artifact_id)

        # Save to database
        created_artifact = await asyncio.to_thread(
            store.artifacts.create_artifact, artifact
        )

        return artifact_to_response(created_artifact)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create artifact: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to create artifact: {str(e)}"
        )
