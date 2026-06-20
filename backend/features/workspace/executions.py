"""
Workspace Executions API Routes.

Handles Playbook Runtime execution management, SSE streaming, and control APIs.
"""

import asyncio
import logging
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query

from backend.app.core.ports.identity_port import IdentityPort
from backend.app.routes.workspace_dependencies import get_identity_port_or_default
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.stores.stage_results_store import StageResultsStore
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.stores.tool_calls_store import ToolCallsStore
from backend.app.services.task_execution_projection import project_execution_for_api
from backend.app.services.workspace_execution_activity import (
    WorkspaceExecutionActivityStore,
)
from backend.features.workspace.executions_core import (
    ExecutionChatRequest,
    get_execution_chat_payload,
    get_execution_payload,
    list_execution_stage_results_payload,
    list_execution_steps_payload,
    list_execution_tool_calls_payload,
    list_executions_with_steps_payload,
)
from backend.features.workspace.executions_core.chat import post_execution_chat_payload
from backend.features.workspace.executions_core.control import (
    cancel_execution_payload,
    confirm_step_payload,
    reject_step_payload,
)
from backend.features.workspace.executions_core.stream_response import (
    stream_execution_updates_response,
)

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspace-executions"])
logger = logging.getLogger(__name__)


@router.get("/{workspace_id}/executions/{execution_id}/stream")
async def stream_execution_updates(
    workspace_id: str = Path(..., description="Workspace ID"),
    execution_id: str = Path(..., description="Execution ID"),
):
    """
    Stream execution updates via Server-Sent Events (SSE).

    Returns real-time updates for execution status, steps, tool calls, results,
    and chat messages.
    """
    return stream_execution_updates_response(
        workspace_id=workspace_id,
        execution_id=execution_id,
        logger=logger,
    )


@router.post("/{workspace_id}/executions/{execution_id}/steps/{step_id}/confirm")
async def confirm_step(
    workspace_id: str = Path(..., description="Workspace ID"),
    execution_id: str = Path(..., description="Execution ID"),
    step_id: str = Path(..., description="Step ID (MindEvent.id)"),
):
    """
    Confirm step and continue execution to next step.

    Updates ExecutionStep confirmation_status to "confirmed" and resumes execution.
    """
    try:
        return confirm_step_payload(execution_id=execution_id, step_id=step_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to confirm step: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/{workspace_id}/executions/{execution_id}/steps/{step_id}/reject")
async def reject_step(
    workspace_id: str = Path(..., description="Workspace ID"),
    execution_id: str = Path(..., description="Execution ID"),
    step_id: str = Path(..., description="Step ID (MindEvent.id)"),
):
    """
    Reject step.

    Updates ExecutionStep confirmation_status to "rejected".
    User can choose to retry or cancel execution.
    """
    try:
        return reject_step_payload(execution_id=execution_id, step_id=step_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to reject step: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/{workspace_id}/executions/{execution_id}/cancel")
async def cancel_execution(
    workspace_id: str = Path(..., description="Workspace ID"),
    execution_id: str = Path(..., description="Execution ID"),
):
    """
    Cancel execution.

    Updates ExecutionSession status to "cancelled" and stops all running
    steps/tool calls.
    """
    try:
        return cancel_execution_payload(execution_id=execution_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to cancel execution: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{workspace_id}/executions/{execution_id}")
async def get_execution(
    workspace_id: str = Path(..., description="Workspace ID"),
    execution_id: str = Path(..., description="Execution ID"),
):
    """
    Get execution session details.

    Returns ExecutionSession view model with full execution context.
    """
    try:
        store = MindscapeStore()
        tasks_store = TasksStore(db_path=store.db_path)
        return get_execution_payload(
            store=store,
            tasks_store=tasks_store,
            workspace_id=workspace_id,
            execution_id=execution_id,
            logger=logger,
        )

    except HTTPException:
        raise
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except Exception as exc:
        logger.error(f"Failed to get execution: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{workspace_id}/executions/{execution_id}/steps")
async def list_execution_steps(
    workspace_id: str = Path(..., description="Workspace ID"),
    execution_id: str = Path(..., description="Execution ID"),
):
    """
    List all steps for an execution.

    Returns list of ExecutionStep view models.
    """
    try:
        store = MindscapeStore()
        return list_execution_steps_payload(
            store=store,
            workspace_id=workspace_id,
            execution_id=execution_id,
            logger=logger,
        )

    except Exception as exc:
        logger.error(f"Failed to list execution steps: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{workspace_id}/executions/{execution_id}/tool-calls")
async def list_execution_tool_calls(
    workspace_id: str = Path(..., description="Workspace ID"),
    execution_id: str = Path(..., description="Execution ID"),
    step_id: Optional[str] = Query(None, description="Optional step ID to filter by"),
):
    """
    List all tool calls for a specific execution.

    Returns list of ToolCall objects for the execution.
    """
    try:
        store = MindscapeStore()
        tool_calls_store = ToolCallsStore(db_path=store.db_path)
        return list_execution_tool_calls_payload(
            tool_calls_store=tool_calls_store,
            execution_id=execution_id,
            step_id=step_id,
        )

    except Exception as exc:
        logger.error(f"Failed to list execution tool calls: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{workspace_id}/executions/{execution_id}/stage-results")
async def list_execution_stage_results(
    workspace_id: str = Path(..., description="Workspace ID"),
    execution_id: str = Path(..., description="Execution ID"),
    step_id: Optional[str] = Query(None, description="Optional step ID to filter by"),
):
    """
    List all stage results for a specific execution.

    Returns list of StageResult objects for the execution.
    """
    try:
        store = MindscapeStore()
        stage_results_store = StageResultsStore(db_path=store.db_path)
        return list_execution_stage_results_payload(
            stage_results_store=stage_results_store,
            execution_id=execution_id,
            step_id=step_id,
        )

    except Exception as exc:
        logger.error(f"Failed to list execution stage results: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{workspace_id}/executions")
async def list_executions(
    workspace_id: str = Path(..., description="Workspace ID"),
    limit: int = Query(30, ge=1, le=200, description="Maximum number of executions"),
    offset: int = Query(0, ge=0, description="Execution list offset"),
    status: Optional[List[str]] = Query(
        None,
        description="Execution statuses to include",
    ),
    playbook_code_prefix: Optional[str] = Query(
        None, description="Filter by playbook code prefix (e.g., 'ig_')"
    ),
    playbook_code: Optional[List[str]] = Query(
        None, description="Filter by exact playbook code"
    ),
    exclude_playbook_code: Optional[List[str]] = Query(
        None, description="Exact playbook codes to exclude"
    ),
    parent_execution_id: Optional[str] = Query(
        None,
        description="Filter child executions by exact parent execution ID",
    ),
    active_only: bool = Query(
        False,
        description="Use active execution defaults and hide admission-deferred rows",
    ),
    order_by: str = Query("created_at", description="Field to order by"),
    order: str = Query("desc", description="Sort order: asc or desc"),
    include_execution_context: bool = Query(
        False,
        description=(
            "Legacy parameter. Execution lists always return compact projection context."
        ),
    ),
):
    """
    List all Playbook executions for a workspace.

    Returns list of ExecutionSession view models grouped by status.
    """
    try:
        activity_store = WorkspaceExecutionActivityStore()
        payload = await asyncio.to_thread(
            activity_store.list_executions,
            workspace_id=workspace_id,
            limit=limit,
            offset=offset,
            statuses=status,
            playbook_code=playbook_code,
            playbook_code_prefix=playbook_code_prefix,
            parent_execution_id=parent_execution_id,
            exclude_playbook_code=exclude_playbook_code,
            active_only=active_only,
            order_by=order_by,
            order=order,
        )
        executions = [
            project_execution_for_api(item, queue_position=None, queue_total=None)
            for item in payload["executions"]
        ]
        return {
            "executions": executions,
            "limit": payload["limit"],
            "offset": payload["offset"],
            "returned": payload["returned"],
            "has_more": payload["has_more"],
            "next_offset": payload["next_offset"],
        }

    except Exception as exc:
        logger.error(f"Failed to list executions: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{workspace_id}/executions-with-steps")
async def list_executions_with_steps(
    workspace_id: str = Path(..., description="Workspace ID"),
    limit: int = Query(50, description="Maximum number of executions to return"),
    include_steps_for: str = Query(
        "active",
        description="Include steps for: 'active' (running/paused), 'all', or 'none'",
    ),
):
    """
    List all Playbook executions for a workspace with their steps in one request.
    """
    try:
        store = MindscapeStore()
        tasks_store = TasksStore(db_path=store.db_path)
        return list_executions_with_steps_payload(
            store=store,
            tasks_store=tasks_store,
            workspace_id=workspace_id,
            limit=limit,
            include_steps_for=include_steps_for,
            logger=logger,
        )

    except Exception as exc:
        logger.error(f"Failed to list executions with steps: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{workspace_id}/executions/{execution_id}/workflow")
async def get_execution_workflow(
    workspace_id: str = Path(..., description="Workspace ID"),
    execution_id: str = Path(..., description="Execution ID"),
):
    """
    Get workflow execution result and handoff plan for multi-step workflows.

    Returns workflow result with step statuses and handoff plan if available.
    """
    try:
        store = MindscapeStore()
        tasks_store = TasksStore(db_path=store.db_path)
        task = tasks_store.get_task_by_execution_id(execution_id)

        if not task:
            raise HTTPException(status_code=404, detail="Execution not found")

        workflow_result = None
        handoff_plan = None

        if task.execution_context:
            workflow_result_data = task.execution_context.get("workflow_result")
            handoff_plan_data = task.execution_context.get("handoff_plan")

            if workflow_result_data:
                workflow_result = workflow_result_data

            if handoff_plan_data:
                handoff_plan = handoff_plan_data

        return {
            "workflow_result": workflow_result,
            "handoff_plan": handoff_plan,
            "execution_id": execution_id,
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to get execution workflow: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{workspace_id}/executions/{execution_id}/chat")
async def get_execution_chat(
    workspace_id: str = Path(..., description="Workspace ID"),
    execution_id: str = Path(..., description="Execution ID"),
    limit: int = Query(100, description="Maximum number of messages to return"),
):
    """
    Get execution chat messages.

    Returns list of ExecutionChatMessage view models for the specified execution.
    """
    try:
        store = MindscapeStore()
        return get_execution_chat_payload(
            store=store,
            workspace_id=workspace_id,
            execution_id=execution_id,
            limit=limit,
            logger=logger,
        )

    except Exception as exc:
        logger.error(f"Failed to get execution chat: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/{workspace_id}/executions/{execution_id}/chat")
async def post_execution_chat(
    workspace_id: str = Path(..., description="Workspace ID"),
    execution_id: str = Path(..., description="Execution ID"),
    request: ExecutionChatRequest = Body(...),
    profile_id: str = Query("default-user", description="User profile ID"),
    identity_port: IdentityPort = Depends(get_identity_port_or_default),
):
    """
    Post a new execution chat message.

    Creates a MindEvent with event_type=EXECUTION_CHAT and returns the created
    message. The assistant reply will be generated asynchronously and pushed via
    SSE.
    """
    return await post_execution_chat_payload(
        workspace_id=workspace_id,
        execution_id=execution_id,
        request=request,
        profile_id=profile_id,
        identity_port=identity_port,
        logger=logger,
    )
