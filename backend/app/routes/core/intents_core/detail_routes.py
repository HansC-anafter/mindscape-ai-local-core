import asyncio
import uuid

from fastapi import APIRouter, Body, HTTPException, Path, Query

from backend.app.models.mindscape import IntentCard, IntentStatus, PriorityLevel

from .schemas import CreateIntentRequest, UpdateIntentRequest
from .serializers import intent_card_to_response
from .state import _utc_now, logger, store

router = APIRouter()

@router.get("/intents/{intent_id}")
async def get_intent(intent_id: str = Path(..., description="Intent ID")):
    """
    Get a single intent by ID
    """
    try:
        intent_card = await asyncio.to_thread(store.get_intent, intent_id)
        if not intent_card:
            raise HTTPException(status_code=404, detail=f"Intent {intent_id} not found")

        # Get workspace_id from metadata or find it via profile_id
        workspace_id = (
            intent_card.metadata.get("workspace_id") if intent_card.metadata else None
        )

        if not workspace_id:
            # Try to find workspace by profile_id
            workspaces = await asyncio.to_thread(
                store.list_workspaces, owner_user_id=intent_card.profile_id
            )
            if workspaces:
                workspace_id = workspaces[0].id
            else:
                workspace_id = ""  # Fallback

        return intent_card_to_response(intent_card, workspace_id)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get intent {intent_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get intent: {str(e)}")


@router.post("/intents", status_code=201)
async def create_intent(request: CreateIntentRequest = Body(...)):
    """
    Create a new intent
    """
    try:
        # Validate workspace exists
        workspace = await store.get_workspace(request.workspace_id)
        if not workspace:
            raise HTTPException(
                status_code=404, detail=f"Workspace {request.workspace_id} not found"
            )

        profile_id = workspace.owner_user_id

        # Map API status to IntentStatus
        status_map = {
            "CONFIRMED": IntentStatus.ACTIVE,
            "CANDIDATE": IntentStatus.PAUSED,
            "REJECTED": IntentStatus.ARCHIVED,
        }
        intent_status = status_map.get(
            request.status.upper() if request.status else "CONFIRMED",
            IntentStatus.ACTIVE,
        )

        # Prepare metadata
        metadata = request.metadata.copy() if request.metadata else {}
        metadata["workspace_id"] = request.workspace_id

        # Create IntentCard
        intent_card = IntentCard(
            id=str(uuid.uuid4()),
            profile_id=profile_id,
            title=request.title,
            description=request.description or "",
            status=intent_status,
            priority=PriorityLevel.MEDIUM,
            tags=[],
            storyline_tags=request.storyline_tags or [],
            category=None,
            progress_percentage=0,
            created_at=_utc_now(),
            updated_at=_utc_now(),
            parent_intent_id=request.parent_id,
            child_intent_ids=[],
            metadata=metadata,
        )

        # Handle parent-child relationship
        if request.parent_id:
            parent_intent = await asyncio.to_thread(store.get_intent, request.parent_id)
            if parent_intent:
                if intent_card.id not in parent_intent.child_intent_ids:
                    parent_intent.child_intent_ids.append(intent_card.id)
                    parent_intent.updated_at = _utc_now()
                    await asyncio.to_thread(store.intents.update_intent, parent_intent)

        # Create intent
        created_intent = await asyncio.to_thread(store.create_intent, intent_card)

        return intent_card_to_response(created_intent, request.workspace_id)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create intent: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to create intent: {str(e)}"
        )


@router.put("/intents/{intent_id}")
async def update_intent(
    intent_id: str = Path(..., description="Intent ID"),
    request: UpdateIntentRequest = Body(...),
):
    """
    Update an existing intent
    """
    try:
        # Get existing intent
        intent_card = await asyncio.to_thread(store.get_intent, intent_id)
        if not intent_card:
            raise HTTPException(status_code=404, detail=f"Intent {intent_id} not found")

        existing_workspace_id = (
            intent_card.metadata.get("workspace_id") if intent_card.metadata else None
        )

        if request.metadata and "workspace_id" in request.metadata:
            requested_workspace_id = request.metadata.get("workspace_id")
            if (
                existing_workspace_id
                and requested_workspace_id != existing_workspace_id
            ):
                raise HTTPException(
                    status_code=403,
                    detail=f"Cannot change intent workspace_id from {existing_workspace_id} to {requested_workspace_id}. Workspace isolation is enforced.",
                )
            if not existing_workspace_id:
                existing_workspace_id = requested_workspace_id

        # Update fields if provided
        if request.title is not None:
            intent_card.title = request.title

        if request.description is not None:
            intent_card.description = request.description

        if request.status is not None:
            status_map = {
                "CONFIRMED": IntentStatus.ACTIVE,
                "CANDIDATE": IntentStatus.PAUSED,
                "REJECTED": IntentStatus.ARCHIVED,
            }
            intent_card.status = status_map.get(
                request.status.upper(), IntentStatus.ACTIVE
            )

        if request.storyline_tags is not None:
            intent_card.storyline_tags = request.storyline_tags

        if request.parent_id is not None:
            old_parent_id = intent_card.parent_intent_id

            if old_parent_id != request.parent_id:
                if old_parent_id:
                    old_parent = await asyncio.to_thread(
                        store.get_intent, old_parent_id
                    )
                    if old_parent and intent_id in old_parent.child_intent_ids:
                        old_parent.child_intent_ids.remove(intent_id)
                        old_parent.updated_at = _utc_now()
                        await asyncio.to_thread(store.intents.update_intent, old_parent)

                if request.parent_id:
                    new_parent = await asyncio.to_thread(
                        store.get_intent, request.parent_id
                    )
                    if new_parent:
                        if intent_id not in new_parent.child_intent_ids:
                            new_parent.child_intent_ids.append(intent_id)
                            new_parent.updated_at = _utc_now()
                            await asyncio.to_thread(
                                store.intents.update_intent, new_parent
                            )

                intent_card.parent_intent_id = request.parent_id

        if request.metadata is not None:
            if not intent_card.metadata:
                intent_card.metadata = {}
            preserved_workspace_id = intent_card.metadata.get("workspace_id")
            intent_card.metadata.update(request.metadata)
            if preserved_workspace_id:
                intent_card.metadata["workspace_id"] = preserved_workspace_id
            elif existing_workspace_id:
                intent_card.metadata["workspace_id"] = existing_workspace_id

        intent_card.updated_at = _utc_now()

        updated_intent = await asyncio.to_thread(
            store.intents.update_intent, intent_card
        )
        if not updated_intent:
            raise HTTPException(status_code=500, detail="Failed to update intent")

        workspace_id = (
            updated_intent.metadata.get("workspace_id")
            if updated_intent.metadata
            else ""
        )

        return intent_card_to_response(updated_intent, workspace_id)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update intent {intent_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to update intent: {str(e)}"
        )


@router.delete("/intents/{intent_id}", status_code=204)
async def delete_intent(
    intent_id: str = Path(..., description="Intent ID"),
    cascade: bool = Query(False, description="Delete child intents as well"),
):
    """
    Delete an intent

    If cascade=true, also deletes all child intents.
    Otherwise, child intents will have their parent_id set to None.
    """
    try:
        # Get intent
        intent_card = await asyncio.to_thread(store.get_intent, intent_id)
        if not intent_card:
            raise HTTPException(status_code=404, detail=f"Intent {intent_id} not found")

        # Handle children
        if intent_card.child_intent_ids:
            if cascade:
                # Delete all children recursively
                for child_id in intent_card.child_intent_ids:
                    await delete_intent(child_id, cascade=True)
            else:
                # Remove parent reference from children
                for child_id in intent_card.child_intent_ids:
                    child = await asyncio.to_thread(store.get_intent, child_id)
                    if child:
                        child.parent_intent_id = None
                        child.updated_at = _utc_now()
                        await asyncio.to_thread(store.intents.update_intent, child)

        # Remove from parent's children list
        if intent_card.parent_intent_id:
            parent = await asyncio.to_thread(
                store.get_intent, intent_card.parent_intent_id
            )
            if parent and intent_id in parent.child_intent_ids:
                parent.child_intent_ids.remove(intent_id)
                parent.updated_at = _utc_now()
                await asyncio.to_thread(store.intents.update_intent, parent)

        # Delete intent from database
        success = await asyncio.to_thread(store.intents.delete_intent, intent_id)
        if not success:
            raise HTTPException(
                status_code=500, detail="Failed to delete intent from database"
            )

        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete intent {intent_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to delete intent: {str(e)}"
        )
