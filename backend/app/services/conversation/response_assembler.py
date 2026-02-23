"""
Response Assembler

Shared helpers for serializing MindEvent objects and collecting pending
tasks into the API response format used by both the PipelineCore shim
and the legacy routing path.
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def serialize_events(events: List[Any]) -> List[Dict[str, Any]]:
    """
    Serialize a list of MindEvent objects to API-compatible dicts.

    Args:
        events: List of MindEvent instances.

    Returns:
        List of serialized event dicts.
    """
    result: List[Dict[str, Any]] = []
    for event in events:
        payload = event.payload if isinstance(event.payload, dict) else {}
        entity_ids = event.entity_ids if isinstance(event.entity_ids, list) else []
        metadata = event.metadata if isinstance(event.metadata, dict) else {}

        result.append(
            {
                "id": event.id,
                "timestamp": event.timestamp.isoformat(),
                "actor": (
                    event.actor.value
                    if hasattr(event.actor, "value")
                    else str(event.actor)
                ),
                "channel": event.channel,
                "profile_id": event.profile_id,
                "project_id": event.project_id,
                "workspace_id": event.workspace_id,
                "event_type": (
                    event.event_type.value
                    if hasattr(event.event_type, "value")
                    else str(event.event_type)
                ),
                "payload": payload,
                "entity_ids": entity_ids,
                "metadata": metadata,
            }
        )
    return result


def collect_pending_tasks(tasks_store, workspace_id: str) -> List[Dict[str, Any]]:
    """
    Collect pending and running tasks formatted for the API response.

    Args:
        tasks_store: TasksStore instance.
        workspace_id: Workspace to query.

    Returns:
        List of task summary dicts.
    """
    pending_list = tasks_store.list_pending_tasks(workspace_id)
    running_list = tasks_store.list_running_tasks(workspace_id)

    result: List[Dict[str, Any]] = []
    for task in pending_list + running_list:
        result.append(
            {
                "id": task.id,
                "pack_id": task.pack_id,
                "task_type": task.task_type,
                "status": task.status.value,
                "created_at": (
                    task.created_at.isoformat() if task.created_at else None
                ),
            }
        )
    return result
