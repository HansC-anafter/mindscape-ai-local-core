"""
Intent API routes
RESTful API for managing IntentCard resources

Provides endpoints for:
- Listing intents by workspace
- Getting, creating, updating, and deleting intents
- Building intent tree structures
"""

import logging
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Path, Query, Body
from pydantic import BaseModel, Field

from ...models.mindscape import IntentCard, IntentStatus, PriorityLevel
from ...services.mindscape_store import MindscapeStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["intents"])

# Initialize store (singleton)
store = MindscapeStore()


# ============================================================================
# Request/Response Models
# ============================================================================

class IntentResponse(BaseModel):
    """Intent API response model matching the API draft specification"""
    id: str
    workspace_id: str
    title: str
    description: Optional[str] = None
    status: str  # 'CANDIDATE' | 'CONFIRMED' | 'REJECTED'
    parent_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class IntentTreeNode(IntentResponse):
    """Intent tree node with children"""
    children: Optional[List['IntentTreeNode']] = None


class CreateIntentRequest(BaseModel):
    """Request model for creating a new intent"""
    workspace_id: str
    title: str
    description: Optional[str] = None
    status: Optional[str] = "CONFIRMED"  # Default to CONFIRMED
    parent_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class UpdateIntentRequest(BaseModel):
    """Request model for updating an intent"""
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    parent_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class ListIntentsResponse(BaseModel):
    """Response model for listing intents"""
    intents: List[IntentResponse]


class ListIntentsTreeResponse(BaseModel):
    """Response model for listing intents as a tree"""
    intents: List[IntentTreeNode]


# ============================================================================
# Helper Functions
# ============================================================================

def intent_card_to_response(intent_card: IntentCard, workspace_id: str) -> IntentResponse:
    """Convert IntentCard to API response format"""

    # Map IntentStatus to API status
    status_map = {
        IntentStatus.ACTIVE: "CONFIRMED",
        IntentStatus.COMPLETED: "CONFIRMED",
        IntentStatus.ARCHIVED: "REJECTED",
        IntentStatus.PAUSED: "CANDIDATE",
    }
    api_status = status_map.get(intent_card.status, "CANDIDATE")

    return IntentResponse(
        id=intent_card.id,
        workspace_id=workspace_id,
        title=intent_card.title,
        description=intent_card.description,
        status=api_status,
        parent_id=intent_card.parent_intent_id,
        metadata=intent_card.metadata or {},
        created_at=intent_card.created_at.isoformat() if intent_card.created_at else datetime.utcnow().isoformat(),
        updated_at=intent_card.updated_at.isoformat() if intent_card.updated_at else datetime.utcnow().isoformat(),
    )


def build_intent_tree(intents: List[IntentCard], workspace_id: str) -> List[IntentTreeNode]:
    """Build tree structure from flat intent list"""

    # Convert to response format
    intent_responses = {intent.id: intent_card_to_response(intent, workspace_id) for intent in intents}

    # Create tree nodes
    tree_nodes: Dict[str, IntentTreeNode] = {}
    root_nodes: List[IntentTreeNode] = []

    # First pass: create all nodes
    for intent in intents:
        node = IntentTreeNode(
            **intent_responses[intent.id].dict(),
            children=[]
        )
        tree_nodes[intent.id] = node

    # Second pass: build tree structure
    for intent in intents:
        node = tree_nodes[intent.id]
        if intent.parent_intent_id and intent.parent_intent_id in tree_nodes:
            # Add as child
            parent_node = tree_nodes[intent.parent_intent_id]
            if parent_node.children is None:
                parent_node.children = []
            parent_node.children.append(node)
        else:
            # Root node
            root_nodes.append(node)

    return root_nodes


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/workspaces/{workspace_id}/intents")
async def list_intents(
    workspace_id: str = Path(..., description="Workspace ID"),
    tree: bool = Query(False, description="Return as tree structure"),
    status: Optional[str] = Query(None, description="Filter by status (CANDIDATE, CONFIRMED, REJECTED)")
):
    """
    List all intents for a workspace

    Supports:
    - tree parameter: Returns intents as a tree structure
    - status parameter: Filters intents by status
    """
    try:
        # Get workspace to find owner_user_id (profile_id)
        workspace = store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found")

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
        intents = store.list_intents(
            profile_id=profile_id,
            status=intent_status,
            priority=None
        )

        # Filter by workspace_id in metadata if needed
        # (Intents may be associated with workspace via metadata)
        filtered_intents = []
        for intent in intents:
            intent_workspace_id = intent.metadata.get("workspace_id") if intent.metadata else None
            if intent_workspace_id == workspace_id or not intent_workspace_id:
                # If no workspace_id in metadata, assume it belongs to this workspace
                filtered_intents.append(intent)

        if tree:
            # Build and return tree structure
            tree_nodes = build_intent_tree(filtered_intents, workspace_id)
            return ListIntentsTreeResponse(intents=tree_nodes)
        else:
            # Return flat list
            intent_responses = [intent_card_to_response(intent, workspace_id) for intent in filtered_intents]
            return ListIntentsResponse(intents=intent_responses)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list intents for workspace {workspace_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list intents: {str(e)}")


@router.get("/intents/{intent_id}")
async def get_intent(
    intent_id: str = Path(..., description="Intent ID")
):
    """
    Get a single intent by ID
    """
    try:
        intent_card = store.get_intent(intent_id)
        if not intent_card:
            raise HTTPException(status_code=404, detail=f"Intent {intent_id} not found")

        # Get workspace_id from metadata or find it via profile_id
        workspace_id = intent_card.metadata.get("workspace_id") if intent_card.metadata else None

        if not workspace_id:
            # Try to find workspace by profile_id
            workspaces = store.list_workspaces(owner_user_id=intent_card.profile_id)
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
async def create_intent(
    request: CreateIntentRequest = Body(...)
):
    """
    Create a new intent
    """
    try:
        # Validate workspace exists
        workspace = store.get_workspace(request.workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail=f"Workspace {request.workspace_id} not found")

        profile_id = workspace.owner_user_id

        # Map API status to IntentStatus
        status_map = {
            "CONFIRMED": IntentStatus.ACTIVE,
            "CANDIDATE": IntentStatus.PAUSED,
            "REJECTED": IntentStatus.ARCHIVED,
        }
        intent_status = status_map.get(request.status.upper() if request.status else "CONFIRMED", IntentStatus.ACTIVE)

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
            category=None,
            progress_percentage=0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            parent_intent_id=request.parent_id,
            child_intent_ids=[],
            metadata=metadata
        )

        # Handle parent-child relationship
        if request.parent_id:
            parent_intent = store.get_intent(request.parent_id)
            if parent_intent:
                if intent_card.id not in parent_intent.child_intent_ids:
                    parent_intent.child_intent_ids.append(intent_card.id)
                    parent_intent.updated_at = datetime.utcnow()
                    store.intents.update_intent(parent_intent)

        # Create intent
        created_intent = store.create_intent(intent_card)

        return intent_card_to_response(created_intent, request.workspace_id)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create intent: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create intent: {str(e)}")


@router.put("/intents/{intent_id}")
async def update_intent(
    intent_id: str = Path(..., description="Intent ID"),
    request: UpdateIntentRequest = Body(...)
):
    """
    Update an existing intent
    """
    try:
        # Get existing intent
        intent_card = store.get_intent(intent_id)
        if not intent_card:
            raise HTTPException(status_code=404, detail=f"Intent {intent_id} not found")

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
            intent_card.status = status_map.get(request.status.upper(), IntentStatus.ACTIVE)

        if request.parent_id is not None:
            # Handle parent change
            old_parent_id = intent_card.parent_intent_id

            if old_parent_id != request.parent_id:
                # Remove from old parent's children
                if old_parent_id:
                    old_parent = store.get_intent(old_parent_id)
                    if old_parent and intent_id in old_parent.child_intent_ids:
                        old_parent.child_intent_ids.remove(intent_id)
                        old_parent.updated_at = datetime.utcnow()
                        store.intents.update_intent(old_parent)

                # Add to new parent's children
                if request.parent_id:
                    new_parent = store.get_intent(request.parent_id)
                    if new_parent:
                        if intent_id not in new_parent.child_intent_ids:
                            new_parent.child_intent_ids.append(intent_id)
                            new_parent.updated_at = datetime.utcnow()
                            store.intents.update_intent(new_parent)

                intent_card.parent_intent_id = request.parent_id

        # Update metadata (merge with existing)
        if request.metadata is not None:
            if not intent_card.metadata:
                intent_card.metadata = {}
            intent_card.metadata.update(request.metadata)

        intent_card.updated_at = datetime.utcnow()

        # Save changes
        updated_intent = store.intents.update_intent(intent_card)
        if not updated_intent:
            raise HTTPException(status_code=500, detail="Failed to update intent")

        # Get workspace_id for response
        workspace_id = updated_intent.metadata.get("workspace_id") if updated_intent.metadata else ""

        return intent_card_to_response(updated_intent, workspace_id)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update intent {intent_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update intent: {str(e)}")


@router.delete("/intents/{intent_id}", status_code=204)
async def delete_intent(
    intent_id: str = Path(..., description="Intent ID"),
    cascade: bool = Query(False, description="Delete child intents as well")
):
    """
    Delete an intent

    If cascade=true, also deletes all child intents.
    Otherwise, child intents will have their parent_id set to None.
    """
    try:
        # Get intent
        intent_card = store.get_intent(intent_id)
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
                    child = store.get_intent(child_id)
                    if child:
                        child.parent_intent_id = None
                        child.updated_at = datetime.utcnow()
                        store.intents.update_intent(child)

        # Remove from parent's children list
        if intent_card.parent_intent_id:
            parent = store.get_intent(intent_card.parent_intent_id)
            if parent and intent_id in parent.child_intent_ids:
                parent.child_intent_ids.remove(intent_id)
                parent.updated_at = datetime.utcnow()
                store.intents.update_intent(parent)

        # Delete intent from database
        success = store.intents.delete_intent(intent_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete intent from database")

        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete intent {intent_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete intent: {str(e)}")

