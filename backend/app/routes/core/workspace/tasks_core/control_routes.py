import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi import Path as PathParam
from pydantic import BaseModel, Field

from backend.app.models.workspace import (
    TaskFeedback,
    TaskFeedbackAction,
    TaskFeedbackReasonCode,
)
from backend.app.services.remote_step_resend_service import (
    extract_remote_step_resend_payload,
    resend_remote_workflow_step_child_task,
)
from backend.app.routes.core.execution_dispatch import get_or_create_cloud_connector
from backend.app.services.stores.postgres.task_feedback_store import PostgresTaskFeedbackStore
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.task_status_fix import TaskStatusFixService
from backend.app.services.runner_resources.resource_block_control import (
    ResourceBlockResumeError,
    resume_resource_blocked_task,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class RejectTaskRequest(BaseModel):
    """Request model for rejecting a task"""

    reason_code: Optional[str] = Field(None, description="Rejection reason code")
    comment: Optional[str] = Field(
        None, description="Optional comment explaining rejection"
    )


class ResendRemoteStepTaskRequest(BaseModel):
    """Request model for resending a remote workflow step child task."""

    target_device_id: Optional[str] = Field(
        None,
        description="Optional override target GPU VM / executor device ID",
    )


class ResumeResourceBlockedTaskRequest(BaseModel):
    reason: str = Field(
        ...,
        min_length=1,
        description="Operator reason after changing the node policy or resource profile",
    )


@router.post("/{workspace_id}/tasks/{task_id}/reject")
async def reject_task(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    task_id: str = PathParam(..., description="Task ID"),
    request: RejectTaskRequest = Body(...),
):
    """Reject a task"""
    try:
        tasks_store = TasksStore()
        feedback_store = PostgresTaskFeedbackStore()

        task = tasks_store.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        if task.workspace_id != workspace_id:
            raise HTTPException(
                status_code=403, detail="Task does not belong to this workspace"
            )

        reason_code_enum = None
        if request.reason_code:
            try:
                reason_code_enum = TaskFeedbackReasonCode(request.reason_code)
            except ValueError:
                logger.warning(f"Invalid reason_code: {request.reason_code}")

        feedback = TaskFeedback(
            id=str(uuid.uuid4()),
            task_id=task_id,
            workspace_id=workspace_id,
            user_id="default-user",
            action=TaskFeedbackAction.REJECT,
            reason_code=reason_code_enum,
            comment=request.comment,
        )

        feedback_store.create_feedback(feedback)

        return {
            "success": True,
            "message": "Task rejected successfully",
            "feedback_id": feedback.id,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reject task: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workspace_id}/tasks/{task_id}/cancel")
async def cancel_task(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    task_id: str = PathParam(..., description="Task ID"),
):
    """Cancel a pending or running task"""
    try:
        tasks_store = TasksStore()
        task = tasks_store.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        if task.workspace_id != workspace_id:
            raise HTTPException(
                status_code=403, detail="Task does not belong to this workspace"
            )

        success = tasks_store.cancel_task(task_id)
        if not success:
            raise HTTPException(
                status_code=409,
                detail=f"Task cannot be cancelled (status: {task.status})",
            )
        return {"success": True, "message": "Task cancelled"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel task: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workspace_id}/tasks/{task_id}/resend-remote-step")
async def resend_remote_step_task(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    task_id: str = PathParam(..., description="Task ID"),
    request: Optional[ResendRemoteStepTaskRequest] = Body(None),
):
    """Resend a remote workflow-step child task using its stored request payload."""
    try:
        tasks_store = TasksStore()
        task = tasks_store.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        if task.workspace_id != workspace_id:
            raise HTTPException(
                status_code=403, detail="Task does not belong to this workspace"
            )

        extract_remote_step_resend_payload(task, workspace_id=workspace_id)
        connector = get_or_create_cloud_connector()
        if connector is None:
            raise HTTPException(
                status_code=503,
                detail="Cloud Connector not available for remote step resend",
            )
        return await resend_remote_workflow_step_child_task(
            task=task,
            workspace_id=workspace_id,
            connector=connector,
            target_device_id=request.target_device_id if request else None,
        )
    except HTTPException:
        raise
    except ValueError as e:
        status_code = 503 if "Cloud Connector" in str(e) else 409
        raise HTTPException(status_code=status_code, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to resend remote step task: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail=f"Cloud dispatch failed: {e}")


@router.post("/{workspace_id}/tasks/{task_id}/resume-resource-block")
async def resume_resource_blocked_task_route(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    task_id: str = PathParam(..., description="Task ID"),
    request: ResumeResourceBlockedTaskRequest = Body(...),
):
    """Resume one preserved resource-blocked task after its contract changed."""
    try:
        return await resume_resource_blocked_task(
            workspace_id=workspace_id,
            task_id=task_id,
            reason=request.reason,
        )
    except ResourceBlockResumeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc


@router.post("/{workspace_id}/fix-task-status")
async def fix_task_status(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    create_timeline_items: bool = Query(
        True, description="Create timeline items for fixed tasks"
    ),
    limit: Optional[int] = Query(None, description="Maximum number of tasks to fix"),
):
    """
    Fix tasks with inconsistent status and reap zombie tasks.

    Finds and fixes tasks where:
    - task.status = "running" but execution_context.status = "completed" or "failed"
    - task.status = "running" but heartbeat is stale (zombie reaper)

    This happens when PlaybookRunExecutor didn't properly update task status,
    or when a runner crashes without marking the task as failed.
    """
    try:
        fix_service = TaskStatusFixService()
        result = fix_service.fix_all_inconsistent_tasks(
            workspace_id=workspace_id,
            create_timeline_items=create_timeline_items,
            limit=limit,
        )

        # Also run zombie reaper
        tasks_store = TasksStore()
        reaped_ids = tasks_store.reap_zombie_tasks()
        result["zombie_tasks_reaped"] = len(reaped_ids)
        result["zombie_task_ids"] = reaped_ids

        return result
    except Exception as e:
        logger.error(f"Failed to fix task status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
