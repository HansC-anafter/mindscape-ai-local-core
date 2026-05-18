import asyncio
from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Path, Query

from backend.app.services.mindscape_store import MindscapeStore

from .schemas import BreakGlassApprovalModel, BreakGlassRequestModel
from .state import logger

router = APIRouter()

@router.post("/{workspace_id}/break-glass/request")
async def request_break_glass(
    workspace_id: str = Path(..., description="Workspace ID"),
    request: BreakGlassRequestModel = Body(...),
):
    """
    Request break-glass permission for host access.

    Creates a Decision Card requiring user approval.
    """
    try:
        from backend.app.services.governance.break_glass_service import (
            BreakGlassService,
            BreakGlassRequest,
            get_break_glass_service,
        )

        store = MindscapeStore()
        workspace = await store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        agent_id = request.agent_id or getattr(
            workspace, "resolved_executor_runtime", None
        )
        if not agent_id:
            raise HTTPException(
                status_code=400,
                detail="agent_id required (model-route-registry has no workspace executor route)",
            )

        service = get_break_glass_service()
        permission = await asyncio.to_thread(
            service.request_permission,
            BreakGlassRequest(
                workspace_id=workspace_id,
                agent_id=agent_id,
                operations=request.operations,
                resource_patterns=request.resource_patterns,
                reason=request.reason,
                task_description=request.task_description,
                duration_minutes=request.duration_minutes,
            ),
        )

        return {
            "success": True,
            "permission_id": permission.permission_id,
            "status": permission.status.value,
            "decision_card_id": permission.decision_card_id,
            "message": "Break-glass request created. Awaiting approval.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to request break-glass: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workspace_id}/break-glass/{permission_id}/approve")
async def approve_break_glass(
    workspace_id: str = Path(..., description="Workspace ID"),
    permission_id: str = Path(..., description="Permission ID"),
    request: BreakGlassApprovalModel = Body(...),
    approved_by: str = Query("user", description="Approving user ID"),
):
    """
    Approve or deny a break-glass request.
    """
    try:
        from backend.app.services.governance.break_glass_service import (
            BreakGlassApproval,
            get_break_glass_service,
        )

        service = get_break_glass_service()

        permission = await asyncio.to_thread(
            service.approve_permission,
            BreakGlassApproval(
                permission_id=permission_id,
                approved=request.approved,
                approved_by=approved_by,
                comment=request.comment,
                modified_operations=request.modified_operations,
                modified_duration=request.modified_duration,
            ),
        )

        if not permission:
            raise HTTPException(
                status_code=404, detail="Permission not found or not pending"
            )

        return {
            "success": True,
            "permission_id": permission.permission_id,
            "status": permission.status.value,
            "approved": request.approved,
            "expires_at": (
                permission.expires_at.isoformat() if permission.expires_at else None
            ),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to approve break-glass: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workspace_id}/break-glass")
async def list_break_glass_permissions(
    workspace_id: str = Path(..., description="Workspace ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
):
    """
    List break-glass permissions for a workspace.
    """
    try:
        from backend.app.services.governance.break_glass_service import (
            BreakGlassStatus,
            get_break_glass_service,
        )

        service = get_break_glass_service()

        status_filter = None
        if status:
            try:
                status_filter = BreakGlassStatus(status)
            except ValueError:
                pass

        permissions = await asyncio.to_thread(
            service.list_permissions, workspace_id, status_filter
        )

        return {
            "permissions": [
                {
                    "permission_id": p.permission_id,
                    "agent_id": p.agent_id,
                    "status": p.status.value,
                    "operations": [op.value for op in p.operations],
                    "resource_patterns": p.resource_patterns,
                    "reason": p.reason,
                    "created_at": p.created_at.isoformat(),
                    "expires_at": p.expires_at.isoformat() if p.expires_at else None,
                    "approved_by": p.approved_by,
                }
                for p in permissions
            ],
            "total": len(permissions),
        }

    except Exception as e:
        logger.error(f"Failed to list break-glass: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{workspace_id}/break-glass/{permission_id}")
async def revoke_break_glass(
    workspace_id: str = Path(..., description="Workspace ID"),
    permission_id: str = Path(..., description="Permission ID"),
    revoked_by: str = Query("user", description="Revoking user ID"),
    reason: str = Query("", description="Reason for revocation"),
):
    """
    Revoke an active break-glass permission.
    """
    try:
        from backend.app.services.governance.break_glass_service import (
            get_break_glass_service,
        )

        service = get_break_glass_service()
        permission = await asyncio.to_thread(
            service.revoke_permission, permission_id, revoked_by, reason
        )

        if not permission:
            raise HTTPException(status_code=404, detail="Permission not found")

        return {
            "success": True,
            "permission_id": permission_id,
            "status": permission.status.value,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to revoke break-glass: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
