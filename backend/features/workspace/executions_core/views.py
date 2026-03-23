"""Read-only payload builders for workspace execution routes."""

from __future__ import annotations

from backend.app.models.mindscape import EventType
from backend.app.models.workspace import ExecutionChatMessage

from .serializers import (
    serialize_execution_chat_message,
    serialize_execution_session,
    serialize_stage_result,
    serialize_tool_call,
)
from .step_views import (
    build_step_payloads,
    get_current_step_payload,
    group_step_events_by_execution,
)


def list_execution_tool_calls_payload(*, tool_calls_store, execution_id: str, step_id: str | None):
    """Return serialized tool-call records for one execution."""
    tool_calls = tool_calls_store.list_tool_calls(
        execution_id=execution_id,
        step_id=step_id,
        limit=1000,
    )
    tool_calls_data = [serialize_tool_call(tool_call) for tool_call in tool_calls]
    return {"tool_calls": tool_calls_data, "count": len(tool_calls_data)}


def list_execution_steps_payload(*, store, workspace_id: str, execution_id: str, logger):
    """Return serialized PLAYBOOK_STEP payloads for one execution."""
    events = store.get_events_by_workspace(workspace_id=workspace_id, limit=1000)
    playbook_step_events = [
        event
        for event in events
        if event.event_type == EventType.PLAYBOOK_STEP
        and isinstance(event.payload, dict)
        and event.payload.get("execution_id") == execution_id
    ]
    playbook_step_events.sort(key=lambda event: event.payload.get("step_index", 0))
    steps = build_step_payloads(playbook_step_events, logger=logger)
    return {"steps": steps, "count": len(steps)}


def get_execution_payload(
    *,
    store,
    tasks_store,
    workspace_id: str,
    execution_id: str,
    logger,
):
    """Return one execution session with current-step metadata."""
    task = tasks_store.get_task_by_execution_id(execution_id)
    if not task:
        raise KeyError("Execution not found")
    if task.workspace_id != workspace_id:
        raise PermissionError("Execution belongs to different workspace")

    execution_dict = serialize_execution_session(task)
    if isinstance(execution_dict, dict):
        execution_context = task.execution_context or {}
        current_step_index = execution_context.get("current_step_index", 0)
        events = store.get_events_by_workspace(workspace_id=workspace_id, limit=200)
        current_step = get_current_step_payload(
            events,
            execution_id=execution_id,
            current_step_index=current_step_index,
            logger=logger,
        )
        if current_step is not None:
            execution_dict["current_step"] = current_step
    return execution_dict


def list_execution_stage_results_payload(
    *,
    stage_results_store,
    execution_id: str,
    step_id: str | None,
):
    """Return serialized stage-result records for one execution."""
    stage_results = stage_results_store.list_stage_results(
        execution_id=execution_id,
        step_id=step_id,
        limit=1000,
    )
    stage_results_data = [
        serialize_stage_result(stage_result)
        for stage_result in stage_results
    ]
    return {"stage_results": stage_results_data, "count": len(stage_results_data)}


def list_executions_payload(*, tasks_store, workspace_id: str, limit: int, logger):
    """Return serialized execution sessions for a workspace."""
    execution_tasks = tasks_store.list_executions_by_workspace(
        workspace_id=workspace_id,
        limit=limit,
    )
    executions = []
    for task in execution_tasks:
        try:
            executions.append(serialize_execution_session(task))
        except Exception as exc:
            logger.warning(
                "Failed to create ExecutionSession from task %s: %s",
                task.id,
                exc,
            )
    return {"executions": executions, "count": len(executions)}


def list_executions_with_steps_payload(
    *,
    store,
    tasks_store,
    workspace_id: str,
    limit: int,
    include_steps_for: str,
    logger,
):
    """Return execution sessions with optional embedded step payloads."""
    execution_tasks = tasks_store.list_executions_by_workspace(
        workspace_id=workspace_id,
        limit=limit,
    )

    all_step_events = []
    if include_steps_for != "none":
        events = store.get_events_by_workspace(workspace_id=workspace_id, limit=2000)
        all_step_events = [
            event for event in events if event.event_type == EventType.PLAYBOOK_STEP
        ]

    steps_by_execution = group_step_events_by_execution(all_step_events)

    executions = []
    for task in execution_tasks:
        try:
            execution_dict = serialize_execution_session(task)
            if isinstance(execution_dict, dict):
                execution_id = execution_dict.get("execution_id")
                should_include_steps = False
                if include_steps_for == "all":
                    should_include_steps = True
                elif include_steps_for == "active":
                    is_running = task.status.value == "running"
                    is_paused = execution_dict.get("paused_at") is not None
                    should_include_steps = is_running or is_paused

                if should_include_steps and execution_id in steps_by_execution:
                    execution_dict["steps"] = build_step_payloads(
                        steps_by_execution[execution_id],
                        logger=logger,
                    )
                else:
                    execution_dict["steps"] = []

            executions.append(execution_dict)
        except Exception as exc:
            logger.warning(
                "Failed to create ExecutionSession from task %s: %s",
                task.id,
                exc,
            )

    return {"executions": executions, "count": len(executions)}


def get_execution_chat_payload(
    *,
    store,
    workspace_id: str,
    execution_id: str,
    limit: int,
    logger,
    message_factory=ExecutionChatMessage.from_mind_event,
):
    """Return serialized execution-chat messages for one execution."""
    all_events = store.get_events_by_workspace(workspace_id=workspace_id, limit=limit * 2)
    events = [
        event
        for event in all_events
        if event.event_type == EventType.EXECUTION_CHAT
        and execution_id in (event.entity_ids or [])
    ][:limit]

    messages = []
    for event in events:
        try:
            messages.append(
                serialize_execution_chat_message(message_factory(event))
            )
        except Exception as exc:
            logger.warning(
                "Failed to create ExecutionChatMessage from event %s: %s",
                event.id,
                exc,
            )

    messages.sort(key=lambda message: message.get("created_at", ""))
    return {"messages": messages, "count": len(messages)}
