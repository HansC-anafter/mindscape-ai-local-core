"""
Mindscape Graph Changelog API

REST endpoints for managing graph changelog and pending changes.
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..core.deps import get_current_profile_id

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/execution-graph/changelog", tags=["execution-graph-changelog"]
)


# ==============================================================================
# Request/Response Models
# ==============================================================================


class PendingChangeResponse(BaseModel):
    """Pending change response model"""

    id: str
    workspace_id: str
    version: int
    operation: str
    target_type: str
    target_id: str
    before_state: Optional[dict] = None
    after_state: dict
    actor: str
    actor_context: Optional[str] = None
    status: str
    created_at: Optional[str] = None


class PendingChangesListResponse(BaseModel):
    """List of pending changes"""

    success: bool
    workspace_id: str
    total_pending: int
    changes: List[PendingChangeResponse]


class ApproveRequest(BaseModel):
    """Request to approve/reject changes"""

    change_ids: List[str]
    action: str  # "approve" or "reject"


class ApproveResponse(BaseModel):
    """Response from approve/reject action"""

    success: bool
    processed: int
    success_count: int
    error_count: int
    results: List[dict]


class HistoryEntry(BaseModel):
    """History entry model"""

    id: str
    workspace_id: str
    version: int
    operation: str
    target_type: str
    target_id: str
    actor: str
    status: str
    created_at: Optional[str] = None
    applied_at: Optional[str] = None
    applied_by: Optional[str] = None


class HistoryResponse(BaseModel):
    """Graph changelog history response"""

    success: bool
    workspace_id: str
    current_version: int
    total_entries: int
    history: List[HistoryEntry]


class UndoRequest(BaseModel):
    """Request to undo a change"""

    change_id: str


class UndoResponse(BaseModel):
    """Response from undo action"""

    success: bool
    change_id: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None


# ==============================================================================
# Endpoints
# ==============================================================================


@router.get("")
async def get_mindscape_graph(
    workspace_id: Optional[str] = Query(None, description="Workspace ID"),
    workspace_group_id: Optional[str] = Query(None, description="Workspace Group ID"),
    profile_id: str = Depends(get_current_profile_id),
):
    """
    Get the full mindscape graph for a workspace or workspace group.

    Returns derived nodes + edges with overlay applied.
    This is the main endpoint for the Canvas visualization.
    """
    if not workspace_id and not workspace_group_id:
        raise HTTPException(
            status_code=400,
            detail="Either workspace_id or workspace_group_id is required",
        )

    try:
        import os
        from backend.app.services.mindscape_graph_service import MindscapeGraphService

        # Get database path from environment variable
        db_path = os.environ.get(
            "SQLITE_DB_PATH",
            os.path.join(os.path.dirname(__file__), "..", "..", "data", "mindscape.db"),
        )

        service = MindscapeGraphService(db_path)
        graph = await service.get_graph(
            workspace_id=workspace_id, workspace_group_id=workspace_group_id
        )

        # Convert to JSON-serializable format
        return {
            "nodes": [
                {
                    "id": node.id,
                    "type": node.type,
                    "label": node.label,
                    "status": (
                        node.status.value
                        if hasattr(node.status, "value")
                        else node.status
                    ),
                    "metadata": node.metadata,
                    "created_at": (
                        node.created_at.isoformat() if node.created_at else None
                    ),
                }
                for node in graph.nodes
            ],
            "edges": [
                {
                    "id": edge.id,
                    "from_id": edge.from_id,
                    "to_id": edge.to_id,
                    "type": (
                        edge.type.value if hasattr(edge.type, "value") else edge.type
                    ),
                    "origin": (
                        edge.origin.value
                        if hasattr(edge.origin, "value")
                        else edge.origin
                    ),
                    "confidence": edge.confidence,
                    "status": (
                        edge.status.value
                        if hasattr(edge.status, "value")
                        else edge.status
                    ),
                }
                for edge in graph.edges
            ],
            "overlay": {
                "node_positions": graph.overlay.node_positions,
                "collapsed_state": graph.overlay.collapsed_state,
                "viewport": graph.overlay.viewport,
                "version": graph.overlay.version,
            },
            "scope_type": graph.scope_type,
            "scope_id": graph.scope_id,
            "derived_at": graph.derived_at.isoformat() if graph.derived_at else None,
        }
    except Exception as e:
        logger.error(f"Failed to get mindscape graph: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pending/{workspace_id}", response_model=PendingChangesListResponse)
async def get_pending_changes(
    workspace_id: str,
    actor_filter: Optional[str] = None,
    profile_id: str = Depends(get_current_profile_id),
):
    """
    Get all pending changes for a workspace.

    - **workspace_id**: The workspace ID
    - **actor_filter**: Optional filter by actor (llm, user, system, playbook)
    """
    try:
        from backend.app.services.stores.graph_changelog_store import (
            GraphChangelogStore,
        )

        store = GraphChangelogStore()
        pending = store.get_pending_changes(
            workspace_id=workspace_id,
            actor=actor_filter,
        )

        return PendingChangesListResponse(
            success=True,
            workspace_id=workspace_id,
            total_pending=len(pending),
            changes=[
                PendingChangeResponse(
                    id=c.id,
                    workspace_id=c.workspace_id,
                    version=c.version,
                    operation=c.operation,
                    target_type=c.target_type,
                    target_id=c.target_id,
                    before_state=c.before_state,
                    after_state=c.after_state,
                    actor=c.actor,
                    actor_context=c.actor_context,
                    status=c.status,
                    created_at=c.created_at.isoformat() if c.created_at else None,
                )
                for c in pending
            ],
        )
    except Exception as e:
        logger.error(f"Failed to get pending changes: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pending/{workspace_id}/approve", response_model=ApproveResponse)
async def approve_pending_changes(
    workspace_id: str,
    request: ApproveRequest,
    profile_id: str = Depends(get_current_profile_id),
):
    """
    Approve or reject pending changes.

    - **workspace_id**: The workspace ID
    - **change_ids**: List of change IDs to process
    - **action**: "approve" or "reject"
    """
    if request.action not in ["approve", "reject"]:
        raise HTTPException(
            status_code=400, detail="action must be 'approve' or 'reject'"
        )

    try:
        from backend.app.services.stores.graph_changelog_store import (
            GraphChangelogStore,
        )

        store = GraphChangelogStore()
        results = []
        success_count = 0
        error_count = 0

        for change_id in request.change_ids:
            if request.action == "approve":
                result = store.apply_change(change_id, applied_by=profile_id)
            else:
                result = store.reject_change(change_id)

            results.append(
                {
                    "change_id": change_id,
                    "action": request.action,
                    "success": result.get("success", False),
                    "error": result.get("error"),
                }
            )

            if result.get("success"):
                success_count += 1
            else:
                error_count += 1

        return ApproveResponse(
            success=error_count == 0,
            processed=len(request.change_ids),
            success_count=success_count,
            error_count=error_count,
            results=results,
        )
    except Exception as e:
        logger.error(f"Failed to process pending changes: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{workspace_id}", response_model=HistoryResponse)
async def get_changelog_history(
    workspace_id: str,
    limit: int = 50,
    include_pending: bool = False,
    profile_id: str = Depends(get_current_profile_id),
):
    """
    Get changelog history for a workspace.

    - **workspace_id**: The workspace ID
    - **limit**: Maximum number of entries (default: 50)
    - **include_pending**: Include pending changes in the history
    """
    try:
        from backend.app.services.stores.graph_changelog_store import (
            GraphChangelogStore,
        )

        store = GraphChangelogStore()
        history = store.get_history(
            workspace_id=workspace_id,
            limit=limit,
            include_pending=include_pending,
        )
        current_version = store.get_current_version(workspace_id)

        return HistoryResponse(
            success=True,
            workspace_id=workspace_id,
            current_version=current_version,
            total_entries=len(history),
            history=[
                HistoryEntry(
                    id=h.id,
                    workspace_id=h.workspace_id,
                    version=h.version,
                    operation=h.operation,
                    target_type=h.target_type,
                    target_id=h.target_id,
                    actor=h.actor,
                    status=h.status,
                    created_at=h.created_at.isoformat() if h.created_at else None,
                    applied_at=h.applied_at.isoformat() if h.applied_at else None,
                    applied_by=h.applied_by,
                )
                for h in history
            ],
        )
    except Exception as e:
        logger.error(f"Failed to get history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/undo", response_model=UndoResponse)
async def undo_change(
    request: UndoRequest,
    profile_id: str = Depends(get_current_profile_id),
):
    """
    Undo an applied change.

    - **change_id**: The change ID to undo
    """
    try:
        from backend.app.services.stores.graph_changelog_store import (
            GraphChangelogStore,
        )

        store = GraphChangelogStore()
        result = store.undo_change(request.change_id)

        if result.get("success"):
            return UndoResponse(
                success=True,
                change_id=request.change_id,
                message="變更已成功撤銷",
            )
        else:
            return UndoResponse(
                success=False,
                error=result.get("error", "Unknown error"),
            )
    except Exception as e:
        logger.error(f"Failed to undo change: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/version/{workspace_id}")
async def get_current_version(
    workspace_id: str,
    profile_id: str = Depends(get_current_profile_id),
):
    """
    Get the current applied version for a workspace.
    """
    try:
        from backend.app.services.stores.graph_changelog_store import (
            GraphChangelogStore,
        )

        store = GraphChangelogStore()
        version = store.get_current_version(workspace_id)

        return {
            "success": True,
            "workspace_id": workspace_id,
            "current_version": version,
        }
    except Exception as e:
        logger.error(f"Failed to get version: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
