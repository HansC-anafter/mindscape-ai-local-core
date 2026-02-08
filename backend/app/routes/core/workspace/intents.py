import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import (
    APIRouter,
    HTTPException,
    Path as PathParam,
    Query,
    Body,
)

from ....models.mindscape import (
    IntentTagStatus,
    IntentCard,
    IntentStatus,
    PriorityLevel,
)
from ....services.mindscape_store import MindscapeStore
from ....services.stores.intent_tags_store import IntentTagsStore

router = APIRouter()
logger = logging.getLogger(__name__)
store = MindscapeStore()


@router.get("/{workspace_id}/intent-tags/candidates")
async def get_candidate_intent_tags(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    message_id: Optional[str] = Query(None, description="Filter by message ID"),
    limit: int = Query(10, description="Maximum number of tags to return"),
):
    """
    Get candidate intent tags for a workspace

    Returns list of candidate (not yet confirmed) intent tags, typically shown after user input
    to suggest possible directions the AI sees.
    """
    try:
        intent_tags_store = IntentTagsStore(db_path=store.db_path)

        # Get candidate intent tags for this workspace
        candidate_tags = intent_tags_store.list_intent_tags(
            workspace_id=workspace_id, status=IntentTagStatus.CANDIDATE, limit=limit
        )

        # Filter by message_id if provided
        if message_id:
            candidate_tags = [
                tag for tag in candidate_tags if tag.message_id == message_id
            ]

        # Convert to dict for JSON response
        tags_dict = []
        for tag in candidate_tags:
            tag_dict = {
                "id": tag.id,
                "title": tag.label,  # IntentTag uses 'label' field
                "description": (
                    tag.metadata.get("description") if tag.metadata else None
                ),
                "confidence": tag.confidence,
                "source": tag.source.value,
                "status": tag.status.value,
                "message_id": tag.message_id,
                "created_at": tag.created_at.isoformat() if tag.created_at else None,
            }
            tags_dict.append(tag_dict)

        return {"intent_tags": tags_dict, "count": len(tags_dict)}

    except Exception as e:
        logger.error(f"Failed to get candidate intent tags: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workspace_id}/intent-tags/{intent_tag_id}/confirm")
async def confirm_intent_tag(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    intent_tag_id: str = PathParam(..., description="Intent Tag ID"),
):
    """
    Confirm an intent tag (candidate -> confirmed)

    This action marks a candidate intent as confirmed by the user and writes it to long-term memory (IntentCard).
    Only confirmed intents are written to long-term memory.
    """
    try:
        intent_tags_store = IntentTagsStore(db_path=store.db_path)

        # Get the intent tag to verify it belongs to this workspace
        intent_tag = intent_tags_store.get_intent_tag(intent_tag_id)
        if not intent_tag:
            raise HTTPException(status_code=404, detail="Intent tag not found")

        if intent_tag.workspace_id != workspace_id:
            raise HTTPException(
                status_code=403, detail="Intent tag belongs to different workspace"
            )

        # Confirm the intent
        success = intent_tags_store.confirm_intent(intent_tag_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to confirm intent tag")

        # Write confirmed intent to long-term memory (IntentCard)
        try:
            # Get workspace to find profile_id
            workspace_obj = await store.get_workspace(workspace_id)
            if not workspace_obj:
                logger.warning(
                    f"Workspace {workspace_id} not found, skipping IntentCard creation"
                )
            else:
                profile_id = workspace_obj.owner_user_id

                # Check if IntentCard with same title already exists
                existing_intents = store.list_intents(
                    profile_id=profile_id, status=None, priority=None
                )
                intent_exists = any(
                    intent.title == intent_tag.label or intent_tag.label in intent.title
                    for intent in existing_intents
                )

                if not intent_exists:
                    # Create IntentCard from confirmed IntentTag
                    new_intent = IntentCard(
                        id=str(uuid.uuid4()),
                        profile_id=profile_id,
                        title=intent_tag.label,
                        description=(
                            intent_tag.metadata.get("description", "")
                            if intent_tag.metadata
                            else ""
                        ),
                        status=IntentStatus.ACTIVE,
                        priority=PriorityLevel.MEDIUM,
                        tags=[],
                        category="confirmed_intent_tag",
                        progress_percentage=0.0,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                        started_at=None,
                        completed_at=None,
                        due_date=None,
                        parent_intent_id=None,
                        child_intent_ids=[],
                        metadata={
                            "source": "confirmed_intent_tag",
                            "workspace_id": workspace_id,
                            "intent_tag_id": intent_tag_id,
                            "message_id": intent_tag.message_id,
                            "confidence": intent_tag.confidence,
                        },
                    )
                    store.create_intent(new_intent)
                    logger.info(
                        f"Created IntentCard {new_intent.id} from confirmed IntentTag {intent_tag_id}"
                    )
                else:
                    logger.info(
                        f"IntentCard with title '{intent_tag.label}' already exists, skipping creation"
                    )

        except Exception as e:
            logger.error(
                f"Failed to create IntentCard from confirmed IntentTag: {e}",
                exc_info=True,
            )
            # Don't fail the confirmation if IntentCard creation fails

        return {"success": True, "intent_tag_id": intent_tag_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to confirm intent tag: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{workspace_id}/intent-tags/{intent_tag_id}/label")
async def update_intent_tag_label(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    intent_tag_id: str = PathParam(..., description="Intent Tag ID"),
    request: dict = Body(..., description="Request body with 'label' field"),
):
    """
    Update intent tag label

    Allows users to edit the label of an intent tag.
    """
    try:
        intent_tags_store = IntentTagsStore(db_path=store.db_path)

        # Get the intent tag to verify it belongs to this workspace
        intent_tag = intent_tags_store.get_intent_tag(intent_tag_id)
        if not intent_tag:
            raise HTTPException(status_code=404, detail="Intent tag not found")

        if intent_tag.workspace_id != workspace_id:
            raise HTTPException(
                status_code=403, detail="Intent tag belongs to different workspace"
            )

        # Get label from request body
        label = request.get("label")
        if not label or not isinstance(label, str) or not label.strip():
            raise HTTPException(
                status_code=400,
                detail="Label is required and must be a non-empty string",
            )

        # Update the label
        success = intent_tags_store.update_intent_tag_label(
            intent_tag_id, label.strip()
        )
        if not success:
            raise HTTPException(
                status_code=500, detail="Failed to update intent tag label"
            )

        return {"success": True, "intent_tag_id": intent_tag_id, "label": label}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update intent tag label: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
