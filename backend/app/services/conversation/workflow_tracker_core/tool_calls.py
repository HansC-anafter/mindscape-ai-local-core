"""ToolCall helpers for WorkflowTracker."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional

from backend.app.services.conversation.workflow_tracker_core.clock import utc_now
from backend.app.services.stores.tool_calls_store import ToolCall

logger = logging.getLogger(__name__)


def resolve_factory_cluster(
    *,
    tracker: Any,
    execution_id: str,
    tool_name: str,
    factory_cluster: Optional[str],
) -> str:
    if factory_cluster:
        return factory_cluster

    default_cluster = None
    try:
        from backend.app.services.stores.tasks_store import TasksStore

        tasks_store = TasksStore()
        task = tasks_store.get_task_by_execution_id(execution_id)
        if task and task.execution_context:
            default_cluster = task.execution_context.get("default_cluster")
    except Exception as exc:
        logger.debug("Failed to get default_cluster from task: %s", exc)

    if default_cluster:
        return default_cluster

    connection_id = None
    if "." in tool_name:
        parts = tool_name.split(".", 1)
        if len(parts) >= 1:
            potential_connection_id = parts[0]
            if potential_connection_id and not potential_connection_id.startswith(
                ("filesystem_", "sandbox.", "capability.")
            ):
                connection_id = potential_connection_id

    if connection_id:
        try:
            from backend.app.services.tool_registry import ToolRegistryService

            registry = ToolRegistryService(db_path=tracker.store.db_path)
            connection = registry.get_connection(connection_id)
            if connection and connection.remote_cluster_url:
                return connection.connection_type or "remote"
            if connection:
                return "local_mcp"
            return default_cluster or "local_mcp"
        except Exception as exc:
            logger.debug(
                "Failed to get cluster from connection %s: %s",
                connection_id,
                exc,
            )
            return default_cluster or "local_mcp"

    if tool_name.startswith(("filesystem_", "sandbox.", "local_")) or (
        "mcp" in tool_name.lower()
    ):
        return "local_mcp"

    return default_cluster or "local_mcp"


def record_tool_call_start(
    *,
    tracker: Any,
    execution_id: str,
    step_id: str,
    tool_name: str,
    parameters: Dict[str, Any],
    factory_cluster: Optional[str] = None,
) -> ToolCall:
    tool_call_id = str(uuid.uuid4())
    now = utc_now()
    resolved_factory_cluster = resolve_factory_cluster(
        tracker=tracker,
        execution_id=execution_id,
        tool_name=tool_name,
        factory_cluster=factory_cluster,
    )

    tool_call = ToolCall(
        id=tool_call_id,
        execution_id=execution_id,
        step_id=step_id,
        tool_name=tool_name,
        tool_id=None,
        parameters=parameters,
        response=None,
        status="pending",
        error=None,
        duration_ms=None,
        factory_cluster=resolved_factory_cluster,
        started_at=now,
        completed_at=None,
        created_at=now,
    )

    try:
        tracker.tool_calls_store.create_tool_call(tool_call)
        logger.debug("Created ToolCall record: %s for tool %s", tool_call_id, tool_name)
    except Exception as exc:
        logger.warning("Failed to create ToolCall record: %s", exc)

    return tool_call


def record_tool_call_complete(
    *,
    tracker: Any,
    tool_call_id: str,
    response: Dict[str, Any],
    duration_ms: Optional[int] = None,
) -> bool:
    try:
        return tracker.tool_calls_store.update_tool_call_status(
            tool_call_id=tool_call_id,
            status="completed",
            response=response,
            completed_at=utc_now(),
        )
    except Exception as exc:
        logger.warning("Failed to update ToolCall: %s", exc)
        return False


def record_tool_call_fail(
    *,
    tracker: Any,
    tool_call_id: str,
    error: str,
    duration_ms: Optional[int] = None,
) -> bool:
    try:
        return tracker.tool_calls_store.update_tool_call_status(
            tool_call_id=tool_call_id,
            status="failed",
            error=error,
            completed_at=utc_now(),
        )
    except Exception as exc:
        logger.warning("Failed to update ToolCall: %s", exc)
        return False
