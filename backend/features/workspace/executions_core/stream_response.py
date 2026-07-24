"""SSE response helpers for workspace execution routes."""

import asyncio
import json
import uuid
from datetime import datetime
from typing import AsyncGenerator

from fastapi.responses import StreamingResponse

from backend.app.models.mindscape import EventActor, EventType, MindEvent
from backend.app.models.workspace import (
    ExecutionChatMessage,
    ExecutionChatMessageType,
    ExecutionSession,
    PlaybookExecutionStep,
)
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.stores.stage_results_store import StageResultsStore
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.stores.tool_calls_store import ToolCallsStore
from backend.features.workspace.executions_core import ExecutionStreamEvent


def stream_execution_updates_response(
    *,
    workspace_id: str,
    execution_id: str,
    logger,
) -> StreamingResponse:
    """Build the SSE streaming response for execution updates."""

    async def generate_events() -> AsyncGenerator[str, None]:
        """Generate SSE events for execution updates."""
        store = MindscapeStore()
        tasks_store = TasksStore(db_path=store.db_path)
        tool_calls_store = ToolCallsStore(db_path=store.db_path)
        stage_results_store = StageResultsStore(db_path=store.db_path)

        last_step_timestamp = None
        last_tool_call_timestamp = None
        last_stage_result_timestamp = None
        last_execution_update = None
        last_chat_timestamp = None
        heartbeat_counter = 0

        try:
            while True:
                task = await asyncio.to_thread(
                    tasks_store.get_task_by_execution_id, execution_id
                )
                if not task:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Execution not found'})}\n\n"
                    break

                try:
                    execution = ExecutionSession.from_task(task)

                    execution_dict = (
                        execution.model_dump()
                        if hasattr(execution, "model_dump")
                        else execution
                    )
                    if isinstance(execution_dict, dict):
                        execution_dict["status"] = task.status.value
                    execution_key = (
                        f"{task.status.value}-{execution.current_step_index}-"
                        f"{execution.paused_at}"
                    )
                    if execution_key != last_execution_update:
                        event = ExecutionStreamEvent.execution_update(execution)
                        event["execution"]["status"] = task.status.value
                        yield f"data: {json.dumps(event)}\n\n"
                        last_execution_update = execution_key

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

                        execution_context = task.execution_context or {}
                        playbook_code = (
                            execution_context.get("playbook_code") or task.pack_id
                        )

                        if (
                            playbook_code == "execution_status_query"
                            and task.status.value == "succeeded"
                        ):
                            workflow_result = execution_context.get("workflow_result")
                            if workflow_result and isinstance(workflow_result, dict):
                                report = (
                                    workflow_result.get("report")
                                    or workflow_result.get("outputs", {}).get("report")
                                    or workflow_result.get("output", {}).get("report")
                                    or workflow_result.get("result", {}).get("report")
                                )
                                if report:
                                    message_id = str(uuid.uuid4())
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

                                    await asyncio.to_thread(
                                        store.create_event, message_event
                                    )

                                    query_result_message = ExecutionChatMessage(
                                        id=message_id,
                                        execution_id=execution_id,
                                        role="assistant",
                                        content=report,
                                        message_type=(
                                            ExecutionChatMessageType.SYSTEM_HINT
                                        ),
                                        created_at=datetime.now(),
                                    )

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
                        yield f"data: {json.dumps({'type': 'stream_end'})}\n\n"
                        break

                    events = await asyncio.to_thread(
                        store.get_events_by_workspace,
                        workspace_id=workspace_id,
                        limit=200,
                    )
                    playbook_step_type = EventType.PLAYBOOK_STEP
                    playbook_step_events = [
                        e
                        for e in events
                        if e.event_type == playbook_step_type
                        and isinstance(e.payload, dict)
                        and e.payload.get("execution_id") == execution_id
                    ]

                    execution_chat_events = [
                        e
                        for e in events
                        if e.event_type == EventType.EXECUTION_CHAT
                        and execution_id in (e.entity_ids or [])
                    ]

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
                            except Exception as exc:
                                logger.warning(
                                    f"Failed to create step_update event: {exc}"
                                )

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
                            except Exception as exc:
                                logger.warning(
                                    f"Failed to create execution_chat event: {exc}"
                                )

                    tool_calls = await asyncio.to_thread(
                        tool_calls_store.list_tool_calls,
                        execution_id=execution_id,
                        limit=50,
                    )

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

                    stage_results = await asyncio.to_thread(
                        stage_results_store.list_stage_results,
                        execution_id=execution_id,
                        limit=50,
                    )

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

                except Exception as exc:
                    logger.error(
                        f"Error generating execution events: {exc}", exc_info=True
                    )
                    yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

                heartbeat_counter += 1
                if heartbeat_counter >= 30:
                    yield ": heartbeat\n\n"
                    heartbeat_counter = 0

                await asyncio.sleep(1)

        except asyncio.CancelledError:
            logger.info(f"SSE stream cancelled for execution {execution_id}")
            yield f"data: {json.dumps({'type': 'stream_end'})}\n\n"
        except Exception as exc:
            logger.error(f"SSE stream error: {exc}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
            yield f"data: {json.dumps({'type': 'stream_end'})}\n\n"
        finally:
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
