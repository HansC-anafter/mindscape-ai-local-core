"""
Workspace Executions API Routes

Handles Playbook Runtime execution management, SSE streaming, and control APIs.
"""

import logging
import json
import asyncio
from typing import Dict, Any, Optional, AsyncGenerator
from datetime import datetime
from fastapi import APIRouter, HTTPException, Path, Depends, Query, Body
from fastapi.responses import StreamingResponse

from backend.app.models.workspace import (
    ExecutionSession,
    PlaybookExecutionStep,
    Task,
    ExecutionChatMessage,
)
from backend.app.models.mindscape import MindEvent, EventType
from backend.app.models.playbook import PlaybookMetadata
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.stores.tool_calls_store import ToolCallsStore
from backend.app.services.stores.stage_results_store import StageResultsStore
from backend.app.core.ports.identity_port import IdentityPort
from backend.app.routes.workspace_dependencies import get_identity_port_or_default
from backend.app.services.conversation.execution_chat_agent_service import (
    handle_execution_chat_agent_turn,
)
from backend.app.services.conversation.execution_chat_config import (
    resolve_execution_chat_config,
)
from backend.app.services.conversation.execution_chat_service import (
    generate_execution_chat_reply,
)
from backend.features.workspace.executions_core import (
    ExecutionChatRequest,
    ExecutionStreamEvent,
    get_execution_payload,
    get_execution_chat_payload,
    list_execution_stage_results_payload,
    list_execution_steps_payload,
    list_execution_tool_calls_payload,
    list_executions_payload,
    list_executions_with_steps_payload,
)

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspace-executions"])
logger = logging.getLogger(__name__)


@router.get("/{workspace_id}/executions/{execution_id}/stream")
async def stream_execution_updates(
    workspace_id: str = Path(..., description="Workspace ID"),
    execution_id: str = Path(..., description="Execution ID"),
):
    """
    Stream execution updates via Server-Sent Events (SSE)

    Returns real-time updates for execution status, steps, tool calls, results, and chat messages.
    Event types: execution_update, step_update, tool_call_update, collaboration_update, stage_result, execution_chat, execution_completed
    """

    async def generate_events() -> AsyncGenerator[str, None]:
        """Generate SSE events for execution updates"""
        store = MindscapeStore()
        tasks_store = TasksStore(db_path=store.db_path)
        tool_calls_store = ToolCallsStore(db_path=store.db_path)
        stage_results_store = StageResultsStore(db_path=store.db_path)

        # Track last seen timestamps to avoid duplicate events
        last_step_timestamp = None
        last_tool_call_timestamp = None
        last_stage_result_timestamp = None
        last_execution_update = None
        last_chat_timestamp = None
        heartbeat_counter = 0

        try:
            while True:
                # Get current execution state
                # Use asyncio.to_thread to avoid blocking the event loop
                task = await asyncio.to_thread(
                    tasks_store.get_task_by_execution_id, execution_id
                )
                if not task:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Execution not found'})}\n\n"
                    break

                # Build ExecutionSession from Task
                try:
                    execution = ExecutionSession.from_task(task)

                    # Send execution_update if status changed
                    # Build execution dict with status from task
                    execution_dict = (
                        execution.model_dump()
                        if hasattr(execution, "model_dump")
                        else execution
                    )
                    if isinstance(execution_dict, dict):
                        execution_dict["status"] = task.status.value
                    execution_key = f"{task.status.value}-{execution.current_step_index}-{execution.paused_at}"
                    if execution_key != last_execution_update:
                        event = ExecutionStreamEvent.execution_update(execution)
                        event["execution"][
                            "status"
                        ] = task.status.value  # Add status to event
                        yield f"data: {json.dumps(event)}\n\n"
                        last_execution_update = execution_key

                    # Check for execution completion
                    if task.status.value in [
                        "succeeded",
                        "failed",
                        "cancelled_by_user",
                    ]:
                        if task.status.value == "succeeded":
                            final_status = "completed"
                        elif task.status.value == "cancelled_by_user":
                            final_status = "cancelled"
                        else:
                            final_status = "failed"

                        # For QUERY type playbooks (like execution_status_query), get output result and send to workspace chat
                        execution_context = task.execution_context or {}
                        playbook_code = (
                            execution_context.get("playbook_code") or task.pack_id
                        )

                        if (
                            playbook_code == "execution_status_query"
                            and task.status.value == "succeeded"
                        ):
                            # Get playbook output result from execution_context
                            workflow_result = execution_context.get("workflow_result")
                            if workflow_result and isinstance(workflow_result, dict):
                                # Extract report from playbook output
                                # Try multiple possible locations for report
                                report = (
                                    workflow_result.get("report")
                                    or workflow_result.get("outputs", {}).get("report")
                                    or workflow_result.get("output", {}).get("report")
                                    or workflow_result.get("result", {}).get("report")
                                )
                                if report:
                                    # Send query result as workspace chat message
                                    from backend.app.models.mindscape import (
                                        EventActor,
                                        MindEvent,
                                    )
                                    import uuid

                                    # Create MESSAGE event for workspace chat
                                    message_id = str(uuid.uuid4())
                                    # Get profile_id from execution_context or use default
                                    profile_id = (
                                        execution_context.get("profile_id")
                                        or "default-user"
                                    )
                                    message_event = MindEvent(
                                        id=message_id,
                                        timestamp=datetime.utcnow(),
                                        actor=EventActor.AGENT,
                                        channel="local_workspace",
                                        profile_id=profile_id,
                                        workspace_id=workspace_id,
                                        event_type=EventType.MESSAGE,
                                        payload={
                                            "message": report,
                                            "is_welcome": False,
                                        },
                                        entity_ids=(
                                            [execution_id] if execution_id else []
                                        ),
                                        metadata={},
                                    )

                                    # Create and save MESSAGE event (this will appear in workspace chat)
                                    await asyncio.to_thread(
                                        store.create_event, message_event
                                    )

                                    # Also send as execution_chat for execution panel
                                    from backend.app.models.workspace import (
                                        ExecutionChatMessage,
                                        ExecutionChatMessageType,
                                        ExecutionChatMessageRole,
                                    )

                                    query_result_message = ExecutionChatMessage(
                                        id=message_id,
                                        execution_id=execution_id,
                                        role=ExecutionChatMessageRole.ASSISTANT,
                                        content=report,
                                        message_type=ExecutionChatMessageType.SYSTEM_HINT,
                                        created_at=datetime.now(),
                                    )

                                    # Send as SSE event for execution panel
                                    sse_event = ExecutionStreamEvent.execution_chat(
                                        query_result_message
                                    )
                                    yield f"data: {json.dumps(sse_event, default=str)}\n\n"

                                    logger.info(
                                        f"Sent execution_status_query result to workspace chat: {len(report)} chars"
                                    )

                        event = ExecutionStreamEvent.execution_completed(
                            execution_id, final_status
                        )
                        yield f"data: {json.dumps(event)}\n\n"
                        # Send final event and close connection properly
                        yield f"data: {json.dumps({'type': 'stream_end'})}\n\n"
                        break

                    # Get latest events (PLAYBOOK_STEP and EXECUTION_CHAT)
                    events = await asyncio.to_thread(
                        store.get_events_by_workspace,
                        workspace_id=workspace_id,
                        limit=200,
                    )
                    # Use EventType from module level import (line 17)
                    playbook_step_type = EventType.PLAYBOOK_STEP
                    playbook_step_events = [
                        e
                        for e in events
                        if e.event_type == playbook_step_type
                        and isinstance(e.payload, dict)
                        and e.payload.get("execution_id") == execution_id
                    ]

                    # Get latest execution chat messages
                    execution_chat_events = [
                        e
                        for e in events
                        if e.event_type == EventType.EXECUTION_CHAT
                        and execution_id in (e.entity_ids or [])
                    ]

                    # Send step_update events for new steps
                    for event in playbook_step_events:
                        event_timestamp = (
                            event.timestamp
                            if hasattr(event.timestamp, "__gt__")
                            else (
                                datetime.fromisoformat(str(event.timestamp))
                                if isinstance(event.timestamp, str)
                                else event.timestamp
                            )
                        )
                        if last_step_timestamp is None or (
                            hasattr(event_timestamp, "__gt__")
                            and event_timestamp > last_step_timestamp
                        ):
                            try:
                                step = PlaybookExecutionStep.from_mind_event(event)
                                step_index = (
                                    event.payload.get("step_index", 0)
                                    if isinstance(event.payload, dict)
                                    else 0
                                )
                                sse_event = ExecutionStreamEvent.step_update(
                                    step, step_index
                                )
                                yield f"data: {json.dumps(sse_event, default=str)}\n\n"
                                last_step_timestamp = event_timestamp
                            except Exception as e:
                                logger.warning(
                                    f"Failed to create step_update event: {e}"
                                )

                    # Send execution_chat events for new chat messages
                    for event in execution_chat_events:
                        event_timestamp = (
                            event.timestamp
                            if hasattr(event.timestamp, "__gt__")
                            else (
                                datetime.fromisoformat(str(event.timestamp))
                                if isinstance(event.timestamp, str)
                                else event.timestamp
                            )
                        )
                        if last_chat_timestamp is None or (
                            hasattr(event_timestamp, "__gt__")
                            and event_timestamp > last_chat_timestamp
                        ):
                            try:
                                message = ExecutionChatMessage.from_mind_event(event)
                                sse_event = ExecutionStreamEvent.execution_chat(message)
                                yield f"data: {json.dumps(sse_event, default=str)}\n\n"
                                last_chat_timestamp = event_timestamp
                            except Exception as e:
                                logger.warning(
                                    f"Failed to create execution_chat event: {e}"
                                )

                    # Get latest tool calls
                    tool_calls = await asyncio.to_thread(
                        tool_calls_store.list_tool_calls,
                        execution_id=execution_id,
                        limit=50,
                    )

                    # Send tool_call_update events for new tool calls
                    for tool_call in tool_calls:
                        if (
                            last_tool_call_timestamp is None
                            or tool_call.created_at > last_tool_call_timestamp
                        ):
                            sse_event = ExecutionStreamEvent.tool_call_update(tool_call)
                            yield f"data: {json.dumps(sse_event, default=str)}\n\n"
                            if (
                                last_tool_call_timestamp is None
                                or tool_call.created_at > last_tool_call_timestamp
                            ):
                                last_tool_call_timestamp = tool_call.created_at

                    # Get latest stage results
                    stage_results = await asyncio.to_thread(
                        stage_results_store.list_stage_results,
                        execution_id=execution_id,
                        limit=50,
                    )

                    # Send stage_result events for new stage results
                    for stage_result in stage_results:
                        if (
                            last_stage_result_timestamp is None
                            or stage_result.created_at > last_stage_result_timestamp
                        ):
                            sse_event = ExecutionStreamEvent.stage_result(stage_result)
                            yield f"data: {json.dumps(sse_event, default=str)}\n\n"
                            if (
                                last_stage_result_timestamp is None
                                or stage_result.created_at > last_stage_result_timestamp
                            ):
                                last_stage_result_timestamp = stage_result.created_at

                except Exception as e:
                    logger.error(
                        f"Error generating execution events: {e}", exc_info=True
                    )
                    yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

                # Heartbeat to keep connection alive and allow frontend health detection
                heartbeat_counter += 1
                if heartbeat_counter >= 30:
                    yield ": heartbeat\n\n"
                    heartbeat_counter = 0

                # Poll interval (1 second)
                await asyncio.sleep(1)

        except asyncio.CancelledError:
            logger.info(f"SSE stream cancelled for execution {execution_id}")
            yield f"data: {json.dumps({'type': 'stream_end'})}\n\n"
        except Exception as e:
            logger.error(f"SSE stream error: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            yield f"data: {json.dumps({'type': 'stream_end'})}\n\n"
        finally:
            # Ensure stream is properly closed
            try:
                yield f"data: {json.dumps({'type': 'stream_end'})}\n\n"
            except Exception:
                pass

    return StreamingResponse(
        generate_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{workspace_id}/executions/{execution_id}/steps/{step_id}/confirm")
async def confirm_step(
    workspace_id: str = Path(..., description="Workspace ID"),
    execution_id: str = Path(..., description="Execution ID"),
    step_id: str = Path(..., description="Step ID (MindEvent.id)"),
):
    """
    Confirm step and continue execution to next step

    Updates ExecutionStep confirmation_status to "confirmed" and resumes execution.
    """
    try:
        store = MindscapeStore()
        tasks_store = TasksStore(db_path=store.db_path)

        # Get task/execution
        task = tasks_store.get_task_by_execution_id(execution_id)
        if not task:
            raise HTTPException(status_code=404, detail="Execution not found")

        # Get the MindEvent (step)
        event = store.get_event(step_id)
        if not event or event.event_type != EventType.PLAYBOOK_STEP:
            raise HTTPException(status_code=404, detail="Step not found")

        # Update step confirmation status in payload
        updated_payload = event.payload.copy() if event.payload else {}
        updated_payload["confirmation_status"] = "confirmed"
        updated_metadata = event.metadata.copy() if event.metadata else {}
        updated_metadata["confirmed_at"] = datetime.utcnow().isoformat()

        # Update event in store
        store.update_event(step_id, payload=updated_payload, metadata=updated_metadata)

        # Update execution_context to resume (clear paused_at)
        if task.execution_context:
            task.execution_context["paused_at"] = None
            task.execution_context["current_step_index"] = (
                event.payload.get("step_index", 0) + 1
            )
            tasks_store.update_task(task.id, execution_context=task.execution_context)

        return {
            "status": "confirmed",
            "step_id": step_id,
            "execution_id": execution_id,
            "message": "Step confirmed, execution will continue",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to confirm step: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workspace_id}/executions/{execution_id}/steps/{step_id}/reject")
async def reject_step(
    workspace_id: str = Path(..., description="Workspace ID"),
    execution_id: str = Path(..., description="Execution ID"),
    step_id: str = Path(..., description="Step ID (MindEvent.id)"),
):
    """
    Reject step

    Updates ExecutionStep confirmation_status to "rejected".
    User can choose to retry or cancel execution.
    """
    try:
        store = MindscapeStore()

        # Get the MindEvent (step)
        event = store.get_event(step_id)
        if not event or event.event_type != EventType.PLAYBOOK_STEP:
            raise HTTPException(status_code=404, detail="Step not found")

        # Update step confirmation status in payload
        updated_payload = event.payload.copy() if event.payload else {}
        updated_payload["confirmation_status"] = "rejected"
        updated_metadata = event.metadata.copy() if event.metadata else {}
        updated_metadata["rejected_at"] = datetime.utcnow().isoformat()

        # Update event in store
        store.update_event(step_id, payload=updated_payload, metadata=updated_metadata)

        return {
            "status": "rejected",
            "step_id": step_id,
            "execution_id": execution_id,
            "message": "Step rejected. You can retry or cancel execution.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reject step: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workspace_id}/executions/{execution_id}/cancel")
async def cancel_execution(
    workspace_id: str = Path(..., description="Workspace ID"),
    execution_id: str = Path(..., description="Execution ID"),
):
    """
    Cancel execution

    Updates ExecutionSession status to "cancelled" and stops all running steps/tool calls.
    """
    try:
        store = MindscapeStore()
        tasks_store = TasksStore(db_path=store.db_path)

        # Get task/execution
        task = tasks_store.get_task_by_execution_id(execution_id)
        if not task:
            raise HTTPException(status_code=404, detail="Execution not found")

        # Update task status to CANCELLED_BY_USER
        from backend.app.models.workspace import TaskStatus

        tasks_store.update_task_status(
            task_id=task.id,
            status=TaskStatus.CANCELLED_BY_USER,
            error="Cancelled by user",
        )

        # Update execution_context
        if task.execution_context:
            task.execution_context["failure_type"] = "cancelled_by_user"
            task.execution_context["failure_reason"] = "Execution cancelled by user"
            tasks_store.update_task(task.id, execution_context=task.execution_context)

        # Reload task to get updated status
        task = tasks_store.get_task_by_execution_id(execution_id)

        return {
            "status": "cancelled",
            "execution_id": execution_id,
            "message": "Execution cancelled successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel execution: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workspace_id}/executions/{execution_id}")
async def get_execution(
    workspace_id: str = Path(..., description="Workspace ID"),
    execution_id: str = Path(..., description="Execution ID"),
):
    """
    Get execution session details

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
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get execution: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workspace_id}/executions/{execution_id}/steps")
async def list_execution_steps(
    workspace_id: str = Path(..., description="Workspace ID"),
    execution_id: str = Path(..., description="Execution ID"),
):
    """
    List all steps for an execution

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

    except Exception as e:
        logger.error(f"Failed to list execution steps: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workspace_id}/executions/{execution_id}/tool-calls")
async def list_execution_tool_calls(
    workspace_id: str = Path(..., description="Workspace ID"),
    execution_id: str = Path(..., description="Execution ID"),
    step_id: Optional[str] = Query(None, description="Optional step ID to filter by"),
):
    """
    List all tool calls for a specific execution

    Returns list of ToolCall objects for the execution
    """
    try:
        store = MindscapeStore()
        tool_calls_store = ToolCallsStore(db_path=store.db_path)
        return list_execution_tool_calls_payload(
            tool_calls_store=tool_calls_store,
            execution_id=execution_id,
            step_id=step_id,
        )

    except Exception as e:
        logger.error(f"Failed to list execution tool calls: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workspace_id}/executions/{execution_id}/stage-results")
async def list_execution_stage_results(
    workspace_id: str = Path(..., description="Workspace ID"),
    execution_id: str = Path(..., description="Execution ID"),
    step_id: Optional[str] = Query(None, description="Optional step ID to filter by"),
):
    """
    List all stage results for a specific execution

    Returns list of StageResult objects for the execution
    """
    try:
        store = MindscapeStore()
        stage_results_store = StageResultsStore(db_path=store.db_path)
        return list_execution_stage_results_payload(
            stage_results_store=stage_results_store,
            execution_id=execution_id,
            step_id=step_id,
        )

    except Exception as e:
        logger.error(f"Failed to list execution stage results: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workspace_id}/executions")
async def list_executions(
    workspace_id: str = Path(..., description="Workspace ID"),
    limit: int = Query(50, description="Maximum number of executions to return"),
):
    """
    List all Playbook executions for a workspace

    Returns list of ExecutionSession view models grouped by status:
    - running: status = "running"
    - pending_confirmation: status = "running" AND paused_at IS NOT NULL AND requires_confirmation = true
    - archived: status IN ("succeeded", "failed") AND created_at < 1 hour ago
    """
    try:
        store = MindscapeStore()
        tasks_store = TasksStore(db_path=store.db_path)
        return list_executions_payload(
            tasks_store=tasks_store,
            workspace_id=workspace_id,
            limit=limit,
            logger=logger,
        )

    except Exception as e:
        logger.error(f"Failed to list executions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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
    List all Playbook executions for a workspace with their steps in a single request

    This endpoint avoids N+1 queries by returning executions with their steps in one response.
    Use include_steps_for parameter to control which executions get steps loaded:
    - 'active': Only load steps for running/paused executions (recommended for performance)
    - 'all': Load steps for all executions
    - 'none': Don't load any steps (same as /executions endpoint)
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

    except Exception as e:
        logger.error(f"Failed to list executions with steps: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workspace_id}/executions/{execution_id}/workflow")
async def get_execution_workflow(
    workspace_id: str = Path(..., description="Workspace ID"),
    execution_id: str = Path(..., description="Execution ID"),
):
    """
    Get workflow execution result and handoff plan for multi-step workflows

    Returns workflow result with step statuses and handoff plan if available.
    """
    try:
        from backend.app.services.stores.tasks_store import TasksStore

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
    except Exception as e:
        logger.error(f"Failed to get execution workflow: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workspace_id}/executions/{execution_id}/chat")
async def get_execution_chat(
    workspace_id: str = Path(..., description="Workspace ID"),
    execution_id: str = Path(..., description="Execution ID"),
    limit: int = Query(100, description="Maximum number of messages to return"),
):
    """
    Get execution chat messages

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

    except Exception as e:
        logger.error(f"Failed to get execution chat: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{workspace_id}/executions/{execution_id}/chat")
async def post_execution_chat(
    workspace_id: str = Path(..., description="Workspace ID"),
    execution_id: str = Path(..., description="Execution ID"),
    request: ExecutionChatRequest = Body(...),
    profile_id: str = Query("default-user", description="User profile ID"),
    identity_port: IdentityPort = Depends(get_identity_port_or_default),
):
    """
    Post a new execution chat message

    Creates a MindEvent with event_type=EXECUTION_CHAT and returns the created message.
    The assistant reply will be generated asynchronously and pushed via SSE.

    Aligned with Port architecture using LocalDomainContext.
    """
    try:
        from backend.app.models.workspace import ExecutionChatMessageType
        from backend.app.models.mindscape import EventActor
        import uuid

        store = MindscapeStore()

        # Get LocalDomainContext from identity port
        ctx = await identity_port.get_current_context(
            workspace_id=workspace_id, profile_id=profile_id
        )

        # Validate message_type
        try:
            msg_type = ExecutionChatMessageType(request.message_type)
        except ValueError:
            msg_type = ExecutionChatMessageType.QUESTION

        # Create user message MindEvent (use ctx.workspace_id and ctx.actor_id)
        user_event = MindEvent(
            id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            actor=EventActor.USER,
            channel="workspace",
            profile_id=ctx.actor_id,
            workspace_id=ctx.workspace_id,
            event_type=EventType.EXECUTION_CHAT,
            payload={
                "execution_id": execution_id,
                "step_id": request.step_id,
                "role": "user",
                "speaker": ctx.actor_id,
                "content": request.content,
                "message_type": msg_type.value,
            },
            entity_ids=[execution_id] + ([request.step_id] if request.step_id else []),
            metadata={"is_execution_chat": True},
        )

        # Save user message
        store.create_event(user_event)

        # Create ExecutionChatMessage view model
        user_message = ExecutionChatMessage.from_mind_event(user_event)
        user_message_dict = (
            user_message.model_dump(mode="json")
            if hasattr(user_message, "model_dump")
            else user_message
        )

        # Get playbook metadata and check execution status
        playbook_metadata = None
        should_continue_execution = False
        try:
            from backend.app.services.stores.tasks_store import TasksStore
            from backend.app.services.playbook_service import PlaybookService

            tasks_store = TasksStore(db_path=store.db_path)
            task = tasks_store.get_task_by_execution_id(execution_id)

            if task:
                # Check if execution needs to continue
                task_status = (
                    task.status.value
                    if hasattr(task.status, "value")
                    else str(task.status)
                )
                execution_context = task.execution_context or {}
                paused_at = execution_context.get("paused_at")
                current_step = execution_context.get("current_step", {})
                step_status = (
                    current_step.get("status")
                    if isinstance(current_step, dict)
                    else None
                )
                step_requires_confirmation = (
                    current_step.get("requires_confirmation", False)
                    if isinstance(current_step, dict)
                    else False
                )
                step_confirmation_status = (
                    current_step.get("confirmation_status")
                    if isinstance(current_step, dict)
                    else None
                )

                # Determine if we should continue execution
                should_continue_execution = (
                    task_status == "waiting_confirmation"
                    or task_status == "paused"
                    or paused_at is not None
                    or step_status == "waiting_confirmation"
                    or (
                        step_requires_confirmation
                        and step_confirmation_status == "pending"
                    )
                )

                logger.info(
                    f"Execution {execution_id} status check: task_status={task_status}, paused_at={paused_at}, step_status={step_status}, step_requires_confirmation={step_requires_confirmation}, step_confirmation_status={step_confirmation_status}, should_continue={should_continue_execution}"
                )

                # Get playbook metadata
                if task.execution_context:
                    playbook_code = task.execution_context.get("playbook_code")
                    if playbook_code:
                        playbook_service = PlaybookService(store=store)
                        playbook = await playbook_service.get_playbook(
                            playbook_code=playbook_code,
                            locale=(
                                ctx.workspace.default_locale
                                if hasattr(ctx, "workspace") and ctx.workspace
                                else "zh-TW"
                            ),
                            workspace_id=ctx.workspace_id,
                        )
                        if playbook:
                            playbook_metadata = playbook.metadata
        except Exception as e:
            logger.warning(
                f"Failed to load playbook metadata or check execution status: {e}"
            )

        # Handle execution continuation or chat reply
        async def handle_execution_response():
            """Async task to either continue execution or generate chat reply"""
            try:
                chat_config = resolve_execution_chat_config(playbook_metadata)
                chat_mode = chat_config.mode

                if chat_mode == "agent":
                    logger.info(
                        f"Handling execution chat for {execution_id} via agent mode"
                    )
                    try:
                        await handle_execution_chat_agent_turn(
                            execution_id=execution_id,
                            ctx=ctx,
                            user_message=request.content,
                            user_message_id=user_event.id,
                            playbook_metadata=playbook_metadata,
                            profile_id=profile_id,
                        )
                    except Exception as e:
                        logger.error(
                            f"Execution chat agent failed for {execution_id}: {e}",
                            exc_info=True,
                        )
                        await generate_execution_chat_reply(
                            execution_id=execution_id,
                            ctx=ctx,
                            user_message=request.content,
                            user_message_id=user_event.id,
                            playbook_metadata=playbook_metadata,
                        )
                elif should_continue_execution:
                    # Scenario A: Continue execution
                    logger.info(
                        f"Auto-continuing execution {execution_id} via execution chat"
                    )
                    from backend.app.services.playbook_runner import PlaybookRunner

                    playbook_runner = PlaybookRunner()

                    try:
                        result = await playbook_runner.continue_playbook_execution(
                            execution_id=execution_id,
                            user_message=request.content,
                            profile_id=profile_id,
                        )
                        logger.info(f"Successfully continued execution {execution_id}")
                    except Exception as e:
                        logger.error(
                            f"Failed to continue execution {execution_id}: {e}",
                            exc_info=True,
                        )
                        # Fallback to chat reply if continue fails
                        await generate_execution_chat_reply(
                            execution_id=execution_id,
                            ctx=ctx,
                            user_message=request.content,
                            user_message_id=user_event.id,
                            playbook_metadata=playbook_metadata,
                        )
                else:
                    # Scenario B: Generate chat reply (discussion mode)
                    logger.info(
                        f"Generating chat reply for execution {execution_id} (discussion mode)"
                    )
                    result = await generate_execution_chat_reply(
                        execution_id=execution_id,
                        ctx=ctx,
                        user_message=request.content,
                        user_message_id=user_event.id,
                        playbook_metadata=playbook_metadata,
                    )
                    # Assistant message is already saved in generate_execution_chat_reply
                    # SSE stream will automatically detect and push it
                    logger.info(
                        f"Generated assistant reply for execution {execution_id}"
                    )
            except Exception as e:
                logger.error(f"Failed to handle execution response: {e}", exc_info=True)

        # Start async task (non-blocking)
        asyncio.create_task(handle_execution_response())

        return {"message": user_message_dict, "status": "sent"}

    except Exception as e:
        logger.error(f"Failed to post execution chat: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
