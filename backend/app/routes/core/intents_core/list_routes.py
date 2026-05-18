import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Path, Query

from backend.app.models.mindscape import IntentStatus

from .schemas import ListIntentsResponse, ListIntentsTreeResponse
from .serializers import build_intent_tree, intent_card_to_response
from .state import _utc_now, logger, store

router = APIRouter()

@router.get("/workspaces/{workspace_id}/intents")
async def list_intents(
    workspace_id: str = Path(..., description="Workspace ID"),
    tree: bool = Query(False, description="Return as tree structure"),
    status: Optional[str] = Query(
        None, description="Filter by status (CANDIDATE, CONFIRMED, REJECTED)"
    ),
):
    """
    List all intents for a workspace

    Supports:
    - tree parameter: Returns intents as a tree structure
    - status parameter: Filters intents by status
    """
    try:
        # Get workspace to find owner_user_id (profile_id)
        workspace = await store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(
                status_code=404, detail=f"Workspace {workspace_id} not found"
            )

        profile_id = workspace.owner_user_id

        # Map API status to IntentStatus if provided
        intent_status = None
        if status:
            status_map = {
                "CONFIRMED": IntentStatus.ACTIVE,
                "CANDIDATE": IntentStatus.PAUSED,
                "REJECTED": IntentStatus.ARCHIVED,
            }
            intent_status = status_map.get(status.upper())

        # Get intents
        intents = await asyncio.to_thread(
            store.list_intents,
            profile_id=profile_id,
            status=intent_status,
            priority=None,
        )

        owner_workspaces = await asyncio.to_thread(
            store.workspaces.list_workspaces, owner_user_id=profile_id, limit=5
        )
        is_single_workspace_owner = (
            len(owner_workspaces) == 1 and owner_workspaces[0].id == workspace_id
        )

        filtered_intents = []
        for intent in intents:
            intent_workspace_id = (
                intent.metadata.get("workspace_id") if intent.metadata else None
            )

            if intent_workspace_id == workspace_id:
                filtered_intents.append(intent)
            elif not intent_workspace_id and is_single_workspace_owner:
                # Backfill workspace_id only when the owner has a single workspace.
                if not intent.metadata:
                    intent.metadata = {}
                intent.metadata["workspace_id"] = workspace_id
                intent.updated_at = _utc_now()
                try:
                    updated = await asyncio.to_thread(
                        store.intents.update_intent, intent
                    )
                    filtered_intents.append(updated or intent)
                except Exception as e:
                    logger.warning(
                        f"Failed to backfill workspace_id for intent {intent.id}: {e}"
                    )

        if tree:
            # Build and return tree structure
            tree_nodes = build_intent_tree(filtered_intents, workspace_id)
            return ListIntentsTreeResponse(intents=tree_nodes)
        else:
            # Return flat list
            intent_responses = [
                intent_card_to_response(intent, workspace_id)
                for intent in filtered_intents
            ]
            return ListIntentsResponse(intents=intent_responses)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to list intents for workspace {workspace_id}: {e}", exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"Failed to list intents: {str(e)}")
