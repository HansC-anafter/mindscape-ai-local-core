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
        tasks_store = TasksStore()

        if include_completed:
            all_tasks = tasks_store.list_tasks_by_workspace(workspace_id, limit=limit)
        else:
            pending = tasks_store.list_pending_tasks(workspace_id)
            running = tasks_store.list_running_tasks(workspace_id)
            all_tasks = (pending + running)[:limit]

        return {"tasks": [task.model_dump() for task in all_tasks]}
    except Exception as e:
        logger.error(f"Failed to get workspace tasks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workspace_id}/executions")
async def get_workspace_executions(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    limit: int = Query(30, ge=1, le=200, description="Maximum number of executions"),
    playbook_code_prefix: Optional[str] = Query(
        None, description="Filter by playbook code prefix (e.g., 'ig_')"
    ),
    playbook_code: Optional[str] = Query(
        None, description="Filter by exact playbook code"
    ),
    order_by: str = Query("created_at", description="Field to order by"),
    order: str = Query("desc", description="Sort order: asc or desc"),
):
    """List executions (tasks) for a workspace with optional playbook filters."""
    try:
        from sqlalchemy import text

        tasks_store = TasksStore()

        query_parts = ["SELECT * FROM tasks WHERE workspace_id = :workspace_id"]
        params: dict = {"workspace_id": workspace_id}

        if playbook_code:
            query_parts.append("AND pack_id = :pack_id")
            params["pack_id"] = playbook_code
        elif playbook_code_prefix:
            query_parts.append("AND pack_id LIKE :pack_prefix")
            params["pack_prefix"] = f"{playbook_code_prefix}%"

        safe_order = "DESC" if order.lower() == "desc" else "ASC"
        safe_col = "created_at"
        if order_by in ("created_at", "started_at", "completed_at", "status"):
            safe_col = order_by
        query_parts.append(f"ORDER BY {safe_col} {safe_order}")

        query_parts.append("LIMIT :limit")
        params["limit"] = limit

        with tasks_store.get_connection() as conn:
            rows = conn.execute(text(" ".join(query_parts)), params).fetchall()
            tasks = [tasks_store._row_to_task(row) for row in rows]

        return {"executions": [task.model_dump() for task in tasks]}
    except Exception as e:
        logger.error(f"Failed to get workspace executions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workspace_id}/executions/{execution_id}/stream")
async def stream_execution_events(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    execution_id: str = PathParam(..., description="Execution ID"),
):
    """SSE stream for execution progress events.

    For completed/failed/cancelled tasks: sends stream_end immediately.
    For running tasks: sends heartbeat events until completion.
    """
    import asyncio
    import json
    from starlette.responses import StreamingResponse

    tasks_store = TasksStore()

    FAILED_STATUSES = {"failed", "cancelled", "cancelled_by_user", "expired", "FAILED"}
    COMPLETED_STATUSES = {"completed", "succeeded", "SUCCEEDED"}
    TERMINAL_STATUSES = FAILED_STATUSES | COMPLETED_STATUSES

    def _make_terminal_event(task_obj):
        """Build the correct terminal event type for the UI hook."""
        ctx = (
            task_obj.execution_context
            if isinstance(task_obj.execution_context, dict)
            else {}
        )
        raw = (task_obj.status or "").lower().replace(" ", "_")
        if raw in FAILED_STATUSES or task_obj.status in FAILED_STATUSES:
            return json.dumps(
                {
                    "type": "execution_error",
                    "error": ctx.get("error") or f"Execution {raw}",
                    "status": task_obj.status,
                    "execution_context": ctx,
                }
            )
        else:
            return json.dumps(
                {
                    "type": "execution_complete",
                    "status": task_obj.status,
                    "execution_context": ctx,
                }
            )

    async def event_generator():
        # Check initial task status
        task = tasks_store.get_task_by_execution_id(execution_id)
        if not task:
            task = tasks_store.get_task(execution_id)

        if not task:
            yield f"data: {json.dumps({'type': 'execution_error', 'error': 'Execution not found'})}\n\n"
            yield f"data: {json.dumps({'type': 'stream_end'})}\n\n"
            return

        status = (task.status or "").lower().replace(" ", "_")
        if status in TERMINAL_STATUSES or task.status in TERMINAL_STATUSES:
            yield f"data: {_make_terminal_event(task)}\n\n"
            yield f"data: {json.dumps({'type': 'stream_end'})}\n\n"
            return

        # For running tasks: poll and emit progress heartbeats
        for _ in range(600):  # max ~30 min (600 * 3s)
            task = tasks_store.get_task_by_execution_id(execution_id)
            if not task:
                task = tasks_store.get_task(execution_id)
            if not task:
                yield f"data: {json.dumps({'type': 'stream_end'})}\n\n"
                return

            ctx = (
                task.execution_context
                if isinstance(task.execution_context, dict)
                else {}
            )
            status = (task.status or "").lower().replace(" ", "_")

            if status in TERMINAL_STATUSES or task.status in TERMINAL_STATUSES:
                yield f"data: {_make_terminal_event(task)}\n\n"
                yield f"data: {json.dumps({'type': 'stream_end'})}\n\n"
                return

            # Emit a progress-style heartbeat that the UI can display
            yield f"data: {json.dumps({'type': 'progress', 'status': task.status, 'current': 0, 'total': 0})}\n\n"

            await asyncio.sleep(3)

        yield f"data: {json.dumps({'type': 'stream_end'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
