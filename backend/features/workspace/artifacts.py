"""
Workspace Artifacts Routes

Handles /workspaces/{id}/artifacts endpoints.
"""

import logging
import traceback
from typing import Optional
from fastapi import APIRouter, HTTPException, Path, Query, Depends

from backend.app.routes.workspace_schemas import (
    ArtifactsListResponse,
    ArtifactResponse,
)
from backend.app.routes.workspace_dependencies import get_workspace, get_artifacts_store
from backend.app.models.workspace import Workspace
from backend.app.services.stores.artifacts_store import ArtifactsStore

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces-artifacts"])
logger = logging.getLogger(__name__)


@router.get("/{workspace_id}/artifacts", response_model=ArtifactsListResponse)
async def get_workspace_artifacts(
    workspace_id: str = Path(..., description="Workspace ID"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of artifacts"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    workspace: Workspace = Depends(get_workspace),
    artifacts_store: ArtifactsStore = Depends(get_artifacts_store),
):
    """
    Get workspace artifacts

    Returns artifacts from artifacts table (single source of truth).
    Artifacts represent playbook execution outputs displayed in the Outcomes panel.
    """
    try:
        logger.info(
            f"Getting artifacts for workspace {workspace_id} (limit={limit}, offset={offset})"
        )
        artifacts = artifacts_store.list_artifacts_by_workspace(
            workspace_id=workspace_id, limit=limit, offset=offset
        )

        artifact_list = []
        for artifact in artifacts:
            artifact_dict = {
                "id": artifact.id,
                "workspace_id": artifact.workspace_id,
                "intent_id": artifact.intent_id,
                "task_id": artifact.task_id,
                "execution_id": artifact.execution_id,
                "playbook_code": artifact.playbook_code,
                "artifact_type": artifact.artifact_type.value,
                "title": artifact.title,
                "summary": artifact.summary,
                "content": artifact.content,
                "storage_ref": artifact.storage_ref,
                "sync_state": artifact.sync_state,
                "primary_action_type": artifact.primary_action_type.value,
                "metadata": artifact.metadata,
                "created_at": (
                    (
                        artifact.created_at.isoformat() + "Z"
                        if artifact.created_at.tzinfo is None
                        else artifact.created_at.isoformat()
                    )
                    if artifact.created_at
                    else None
                ),
                "updated_at": (
                    (
                        artifact.updated_at.isoformat() + "Z"
                        if artifact.updated_at.tzinfo is None
                        else artifact.updated_at.isoformat()
                    )
                    if artifact.updated_at
                    else None
                ),
            }
            artifact_list.append(artifact_dict)

        logger.info(
            f"Returning {len(artifact_list)} artifacts for workspace {workspace_id}"
        )

        return ArtifactsListResponse(
            workspace_id=workspace_id, total=len(artifact_list), artifacts=artifact_list
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to get workspace artifacts for {workspace_id}: {str(e)}\n{traceback.format_exc()}"
        )
        # Return empty list instead of 500 error if table doesn't exist or other recoverable errors
        import sys

        error_str = str(e).lower()
        if "no such table" in error_str or "table.*does not exist" in error_str:
            logger.warning(f"Artifacts table may not exist yet, returning empty list")
            return ArtifactsListResponse(
                workspace_id=workspace_id, total=0, artifacts=[]
            )
        raise HTTPException(
            status_code=500, detail=f"Failed to get workspace artifacts: {str(e)}"
        )


@router.get("/{workspace_id}/artifacts/{artifact_id}", response_model=ArtifactResponse)
async def get_artifact(
    workspace_id: str = Path(..., description="Workspace ID"),
    artifact_id: str = Path(..., description="Artifact ID"),
    workspace: Workspace = Depends(get_workspace),
    artifacts_store: ArtifactsStore = Depends(get_artifacts_store),
):
    """
    Get artifact by ID

    Returns a single artifact with full details.
    """
    try:
        artifact = artifacts_store.get_artifact(artifact_id)
        if not artifact:
            raise HTTPException(status_code=404, detail="Artifact not found")

        if artifact.workspace_id != workspace_id:
            raise HTTPException(
                status_code=403, detail="Artifact does not belong to this workspace"
            )

        return ArtifactResponse(
            id=artifact.id,
            workspace_id=artifact.workspace_id,
            intent_id=artifact.intent_id,
            task_id=artifact.task_id,
            execution_id=artifact.execution_id,
            playbook_code=artifact.playbook_code,
            artifact_type=artifact.artifact_type.value,
            title=artifact.title,
            summary=artifact.summary,
            content=artifact.content,
            storage_ref=artifact.storage_ref,
            sync_state=artifact.sync_state,
            primary_action_type=artifact.primary_action_type.value,
            metadata=artifact.metadata,
            created_at=(
                (
                    artifact.created_at.isoformat() + "Z"
                    if artifact.created_at.tzinfo is None
                    else artifact.created_at.isoformat()
                )
                if artifact.created_at
                else None
            ),
            updated_at=(
                (
                    artifact.updated_at.isoformat() + "Z"
                    if artifact.updated_at.tzinfo is None
                    else artifact.updated_at.isoformat()
                )
                if artifact.updated_at
                else None
            ),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get artifact: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to get artifact: {str(e)}")


@router.get("/{workspace_id}/ig/seeds")
async def get_ig_seeds(
    workspace_id: str = Path(..., description="Workspace ID"),
    workspace: Workspace = Depends(get_workspace),
    artifacts_store: ArtifactsStore = Depends(get_artifacts_store),
):
    """
    Get distinct IG analysis seeds for this workspace with account counts.

    Returns unique target_username values from artifacts with source='ig_analyze_following',
    along with the count of unique accounts discovered for each seed.
    This endpoint is used to populate the Seeds dropdown filter in the IG Workbench.
    """
    import json

    try:
        # Use list_artifacts_by_workspace to get all IG artifacts
        all_artifacts = artifacts_store.list_artifacts_by_workspace(
            workspace_id=workspace_id, limit=500, offset=0
        )

        # seed -> set of unique account handles
        seed_accounts: dict = {}

        for a in all_artifacts:
            meta = a.metadata
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except:
                    continue
            if not isinstance(meta, dict):
                continue

            source = meta.get("source", "")
            if "ig_analyze_following" not in str(source):
                continue

            seed = meta.get("target_username") or meta.get("target_seed")
            if not seed:
                continue

            if seed not in seed_accounts:
                seed_accounts[seed] = set()

            # Extract account handles from artifact content
            content = a.content
            if isinstance(content, str):
                try:
                    content = json.loads(content)
                except:
                    continue

            if isinstance(content, dict):
                # Try both 'accounts' and 'discovered_accounts' keys
                discovered = content.get("accounts") or content.get(
                    "discovered_accounts", []
                )
                if isinstance(discovered, list):
                    for acc in discovered:
                        if isinstance(acc, dict):
                            handle = acc.get("username") or acc.get("handle")
                            if handle:
                                seed_accounts[seed].add(handle)

        # Build response with counts
        seeds_with_counts = [
            {"seed": seed, "count": len(handles)}
            for seed, handles in seed_accounts.items()
        ]
        seeds_with_counts.sort(key=lambda x: (-x["count"], x["seed"]))

        logger.info(
            f"Found {len(seeds_with_counts)} IG seeds for workspace {workspace_id}"
        )

        return {
            "workspace_id": workspace_id,
            "seeds": [s["seed"] for s in seeds_with_counts],
            "seeds_with_counts": seeds_with_counts,
            "total": len(seeds_with_counts),
        }
    except Exception as e:
        logger.error(f"Failed to get IG seeds: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to get IG seeds: {str(e)}")
