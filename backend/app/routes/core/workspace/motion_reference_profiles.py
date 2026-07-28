"""Workspace-scoped read facade for one selected motion reference profile."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.workspace import Workspace
from backend.app.routes.workspace_dependencies import get_workspace
from backend.app.services.media_transport.motion_reference_profile_artifact import (
    MotionReferenceProfileArtifactError,
    resolve_selected_motion_reference_profile,
)
from backend.app.services.media_transport.motion_reference_profile_artifact_store import (
    MotionReferenceProfileArtifactStore,
    get_motion_reference_profile_artifact_store,
)

router = APIRouter()


class MotionReferenceProfileChapterResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapter_id: str = Field(min_length=1, max_length=256)
    title: str = Field(min_length=1, max_length=512)
    start_ms: int = Field(ge=0, le=86_400_000)
    end_ms: int = Field(gt=0, le=86_400_000)
    segment_type: str = Field(min_length=1, max_length=64)
    confidence: float | None = None


class MotionReferenceProfileSelectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ready"]
    artifact_id: str = Field(min_length=1, max_length=256)
    reference_profile_id: str = Field(min_length=1, max_length=512)
    source_ref: str = Field(min_length=1, max_length=2048)
    chapter_count: int = Field(ge=1, le=128)
    duration_ms: int = Field(gt=0, le=86_400_000)
    chapters: list[MotionReferenceProfileChapterResponse] = Field(
        min_length=1,
        max_length=128,
    )


@router.get(
    "/{workspace_id}/motion-reference-profiles/selection",
    response_model=MotionReferenceProfileSelectionResponse,
)
async def get_selected_motion_reference_profile(
    workspace_id: str = Path(..., description="Workspace ID"),
    source_ref: str | None = Query(default=None, max_length=2048),
    artifact_id: str | None = Query(default=None, max_length=256),
    workspace: Workspace = Depends(get_workspace),
    artifact_store: MotionReferenceProfileArtifactStore = Depends(
        get_motion_reference_profile_artifact_store
    ),
) -> MotionReferenceProfileSelectionResponse:
    """Resolve one unique terminal profile and return only its bounded UI summary."""

    _ = workspace
    if not str(source_ref or "").strip() and not str(artifact_id or "").strip():
        raise HTTPException(
            status_code=422,
            detail="motion_reference_profile_selection_missing",
        )
    try:
        resolved = resolve_selected_motion_reference_profile(
            artifact_store=artifact_store,
            workspace_id=workspace_id,
            artifact_id=artifact_id,
            source_ref=source_ref,
        )
    except MotionReferenceProfileArtifactError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc
    if resolved is None:
        raise HTTPException(
            status_code=422,
            detail="motion_reference_profile_selection_missing",
        )
    return MotionReferenceProfileSelectionResponse.model_validate(
        resolved.selection_payload()
    )


__all__ = [
    "MotionReferenceProfileChapterResponse",
    "MotionReferenceProfileSelectionResponse",
    "get_selected_motion_reference_profile",
    "router",
]
