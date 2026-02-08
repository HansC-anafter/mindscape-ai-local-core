import logging
import uuid
from typing import Optional

from fastapi import (
    APIRouter,
    HTTPException,
    Path as PathParam,
    Query,
    Body,
)
from pydantic import BaseModel, Field

from ....services.mindscape_store import MindscapeStore
from ....services.stores.tasks_store import TasksStore
from ....services.stores.task_feedback_store import TaskFeedbackStore
from ....models.workspace import (
    TaskFeedback,
    TaskFeedbackAction,
    TaskFeedbackReasonCode,
)
from ....services.task_status_fix import TaskStatusFixService

router = APIRouter()
logger = logging.getLogger(__name__)
store = MindscapeStore()


@router.get("/{workspace_id}/tasks")
async def get_workspace_tasks(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of tasks"),
    include_completed: bool = Query(False, description="Include completed tasks"),
):
    """Get tasks for a workspace"""
    try:
        tasks_store = TasksStore(db_path=store.db_path)

        if include_completed:
            all_tasks = tasks_store.list_tasks_by_workspace(workspace_id, limit=limit)
        else:
            pending = tasks_store.list_pending_tasks(workspace_id)
            running = tasks_store.list_running_tasks(workspace_id)
            all_tasks = (pending + running)[:limit]

        return {"tasks": [task.dict() for task in all_tasks]}
    except Exception as e:
        logger.error(f"Failed to get workspace tasks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class RejectTaskRequest(BaseModel):
    """Request model for rejecting a task"""

    reason_code: Optional[str] = Field(None, description="Rejection reason code")
    comment: Optional[str] = Field(
        None, description="Optional comment explaining rejection"
    )


@router.post("/{workspace_id}/tasks/{task_id}/reject")
async def reject_task(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    task_id: str = PathParam(..., description="Task ID"),
    request: RejectTaskRequest = Body(...),
):
    """Reject a task"""
    try:
        tasks_store = TasksStore(db_path=store.db_path)
        feedback_store = TaskFeedbackStore(db_path=store.db_path)

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


@router.post("/{workspace_id}/fix-task-status")
async def fix_task_status(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    create_timeline_items: bool = Query(
        True, description="Create timeline items for fixed tasks"
    ),
    limit: Optional[int] = Query(None, description="Maximum number of tasks to fix"),
):
    """
    Fix tasks with inconsistent status

    Finds and fixes tasks where:
    - task.status = "running"
    - execution_context.status = "completed" or "failed"

    This happens when PlaybookRunExecutor didn't properly update task status.
    """
    try:
        fix_service = TaskStatusFixService()
        result = fix_service.fix_all_inconsistent_tasks(
            workspace_id=workspace_id,
            create_timeline_items=create_timeline_items,
            limit=limit,
        )
        return result
    except Exception as e:
        logger.error(f"Failed to fix task status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
