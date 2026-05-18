
import asyncio
from typing import Any, Dict

from fastapi import APIRouter, Body, HTTPException, Path

from backend.app.services.artifact_review_decision import (
    build_artifact_review_decision,
)
from backend.app.services.visual_acceptance_bundle import (
    VISUAL_ACCEPTANCE_ARTIFACT_KIND,
    persist_visual_acceptance_review_decision,
)
from backend.app.services.visual_acceptance_followup_requests import (
    VISUAL_ACCEPTANCE_FOLLOWUP_ARTIFACT_KIND,
    dispatch_followup_request,
    persist_followup_request_state,
)

from .schemas import (
    CreateArtifactReviewDecisionRequest,
    DispatchArtifactFollowupRequest,
    UpdateArtifactFollowupRequestStateRequest,
)
from .serializers import artifact_to_response
from .state import logger, store

router = APIRouter()

@router.post("/workspaces/{workspace_id}/artifacts/{artifact_id}/review-decision")
async def create_artifact_review_decision(
    workspace_id: str = Path(..., description="Workspace ID"),
    artifact_id: str = Path(..., description="Artifact ID"),
    request: CreateArtifactReviewDecisionRequest = Body(...),
):
    """Persist a review decision for a visual acceptance bundle artifact."""
    try:
        artifact = await asyncio.to_thread(store.artifacts.get_artifact, artifact_id)
        if not artifact:
            raise HTTPException(status_code=404, detail=f"Artifact {artifact_id} not found")
        if artifact.workspace_id != workspace_id:
            raise HTTPException(status_code=403, detail="Artifact does not belong to this workspace")

        metadata = artifact.metadata or {}
        content = artifact.content or {}
        review_bundle_id = (
            metadata.get("review_bundle_id")
            or content.get("review_bundle_id")
        )
        if (
            metadata.get("kind") != VISUAL_ACCEPTANCE_ARTIFACT_KIND
            and not review_bundle_id
        ):
            raise HTTPException(
                status_code=422,
                detail="artifact_not_visual_acceptance_bundle",
            )

        decision_payload = build_artifact_review_decision(
            review_bundle_id=str(review_bundle_id or artifact_id),
            decision=request.decision,
            reviewer_id=request.reviewer_id or "",
            notes=request.notes or "",
            checklist_scores=request.checklist_scores,
            followup_actions=request.followup_actions,
        )
        updated_artifact = await asyncio.to_thread(
            persist_visual_acceptance_review_decision,
            artifact=artifact,
            decision_payload=decision_payload,
            artifacts_store=store.artifacts,
        )
        return {
            "success": True,
            "artifact": artifact_to_response(
                updated_artifact,
                include_content=True,
                include_preview=True,
            ),
            "review_decision": decision_payload,
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(
            "Failed to persist review decision artifact=%s workspace=%s: %s",
            artifact_id,
            workspace_id,
            e,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to persist review decision: {str(e)}",
        )


@router.post("/workspaces/{workspace_id}/artifacts/{artifact_id}/followup-request-state")
async def update_artifact_followup_request_state(
    workspace_id: str = Path(..., description="Workspace ID"),
    artifact_id: str = Path(..., description="Artifact ID"),
    request: UpdateArtifactFollowupRequestStateRequest = Body(...),
):
    """Persist a lifecycle transition for a visual acceptance follow-up request artifact."""
    try:
        artifact = await asyncio.to_thread(store.artifacts.get_artifact, artifact_id)
        if not artifact:
            raise HTTPException(status_code=404, detail=f"Artifact {artifact_id} not found")
        if artifact.workspace_id != workspace_id:
            raise HTTPException(status_code=403, detail="Artifact does not belong to this workspace")

        metadata = artifact.metadata or {}
        if metadata.get("kind") != VISUAL_ACCEPTANCE_FOLLOWUP_ARTIFACT_KIND:
            raise HTTPException(
                status_code=422,
                detail="artifact_not_visual_acceptance_followup_request",
            )

        updated_artifact = await asyncio.to_thread(
            persist_followup_request_state,
            artifact=artifact,
            request_state=request.request_state,
            actor_id=request.actor_id or "",
            notes=request.notes or "",
            execution_ref=request.execution_ref,
            artifacts_store=store.artifacts,
        )
        updated_content = (
            updated_artifact.content
            if isinstance(updated_artifact.content, dict)
            else {}
        )
        return {
            "success": True,
            "artifact": artifact_to_response(
                updated_artifact,
                include_content=True,
                include_preview=True,
            ),
            "request_state": updated_content.get("request_state"),
            "transition": updated_content.get("last_transition"),
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(
            "Failed to persist follow-up request state artifact=%s workspace=%s: %s",
            artifact_id,
            workspace_id,
            e,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to persist follow-up request state: {str(e)}",
        )


@router.post("/workspaces/{workspace_id}/artifacts/{artifact_id}/dispatch-followup")
async def dispatch_artifact_followup(
    workspace_id: str = Path(..., description="Workspace ID"),
    artifact_id: str = Path(..., description="Artifact ID"),
    request: DispatchArtifactFollowupRequest = Body(...),
):
    """Consume a visual acceptance follow-up request and dispatch it downstream."""
    try:
        artifact = await asyncio.to_thread(store.artifacts.get_artifact, artifact_id)
        if not artifact:
            raise HTTPException(status_code=404, detail=f"Artifact {artifact_id} not found")
        if artifact.workspace_id != workspace_id:
            raise HTTPException(status_code=403, detail="Artifact does not belong to this workspace")

        metadata = artifact.metadata or {}
        if metadata.get("kind") != VISUAL_ACCEPTANCE_FOLLOWUP_ARTIFACT_KIND:
            raise HTTPException(
                status_code=422,
                detail="artifact_not_visual_acceptance_followup_request",
            )

        result = await dispatch_followup_request(
            artifact=artifact,
            actor_id=request.actor_id or "",
            notes=request.notes or "",
            artifacts_store=store.artifacts,
        )
        request_artifact = result.get("request_artifact")
        dispatch_artifact = result.get("dispatch_artifact")
        response = {
            "success": True,
            "artifact": artifact_to_response(
                request_artifact,
                include_content=True,
                include_preview=True,
            ),
            "dispatch_artifact": artifact_to_response(
                dispatch_artifact,
                include_content=True,
                include_preview=True,
            ),
            "dispatch_status": result.get("dispatch_status"),
            "dispatch_result": result.get("dispatch_result") or {},
        }
        consumer_artifact = result.get("consumer_artifact")
        if consumer_artifact:
            response["consumer_artifact"] = artifact_to_response(
                consumer_artifact,
                include_content=True,
                include_preview=True,
            )
        return response
    except HTTPException:
        raise
    except ValueError as e:
        detail = str(e)
        status_code = 409 if detail.startswith("followup_request_not_ready:") else 422
        raise HTTPException(status_code=status_code, detail=detail)
    except Exception as e:
        logger.error(
            "Failed to dispatch follow-up artifact=%s workspace=%s: %s",
            artifact_id,
            workspace_id,
            e,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to dispatch follow-up: {str(e)}",
        )
