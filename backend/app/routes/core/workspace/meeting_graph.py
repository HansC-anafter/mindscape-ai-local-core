"""Meeting-owned semantic execution graph for AOL command proof."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Path, Query

from backend.app.models.meeting_graph import (
    MeetingExecutionGraphEdge,
    MeetingExecutionGraphNode,
    MeetingExecutionGraphResponse,
)
from backend.app.models.workspace import Workspace
from backend.app.routes.workspace_dependencies import get_artifacts_store, get_workspace
from backend.app.services.meeting_graph.event_projection import (
    merge_meeting_event_runtime_projection,
)
from backend.app.services.meeting_graph.projection_builder import (
    build_meeting_execution_graph,
)
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.stores.meeting_command_store import MeetingCommandStore
from backend.app.services.stores.object_relation_registry_store import (
    ObjectRelationRegistryStore,
)
from backend.app.services.stores.tasks_store import TasksStore

router = APIRouter()
logger = logging.getLogger(__name__)

__all__ = [
    "MeetingExecutionGraphEdge",
    "MeetingExecutionGraphNode",
    "MeetingExecutionGraphResponse",
    "build_meeting_execution_graph",
    "merge_meeting_event_runtime_projection",
    "get_meeting_execution_graph",
    "router",
]


async def _bounded_graph_lookup(
    label: str,
    lookup,
    *,
    timeout: float = 2.0,
    fallback: Optional[List[Any]] = None,
) -> List[Any]:
    try:
        value = await asyncio.wait_for(asyncio.to_thread(lookup), timeout=timeout)
        return list(value or [])
    except Exception as exc:
        logger.warning("Meeting execution graph %s lookup degraded: %s", label, exc)
        return list(fallback or [])


@router.get(
    "/{workspace_id}/meetings/{meeting_id}/execution-graph",
    response_model=MeetingExecutionGraphResponse,
)
async def get_meeting_execution_graph(
    workspace_id: str = Path(..., description="Workspace ID"),
    meeting_id: str = Path(..., description="Meeting/session ID"),
    limit: int = Query(200, ge=1, le=500, description="Maximum task count"),
    workspace: Workspace = Depends(get_workspace),
    artifacts_store: Any = Depends(get_artifacts_store),
) -> MeetingExecutionGraphResponse:
    del workspace
    command_store = MeetingCommandStore()
    tasks_store = TasksStore()
    relations_store = ObjectRelationRegistryStore()
    event_store = MindscapeStore()

    events_lookup = _bounded_graph_lookup(
        "events",
        lambda: event_store.events.get_events_by_meeting_session(
            meeting_session_id=meeting_id,
            workspace_id=workspace_id,
            limit=limit,
        ),
        timeout=10.0,
    )
    tasks_lookup = _bounded_graph_lookup(
        "tasks",
        lambda: tasks_store.list_tasks_by_meeting_session(
            workspace_id=workspace_id,
            meeting_session_id=meeting_id,
            limit=limit,
        ),
        timeout=2.0,
    )
    commands_lookup = _bounded_graph_lookup(
        "commands",
        lambda: command_store.list_by_meeting(
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            limit=limit,
        ),
        timeout=2.0,
    )
    artifacts_lookup = _bounded_graph_lookup(
        "artifacts",
        lambda: artifacts_store.get_by_thread(
            workspace_id=workspace_id,
            thread_id=meeting_id,
            limit=100,
        ),
        timeout=2.0,
    )
    relations_lookup = _bounded_graph_lookup(
        "relations",
        lambda: relations_store.search(
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            limit=200,
        ),
        timeout=2.0,
    )
    events, commands, tasks, artifacts, relations = await asyncio.gather(
        events_lookup,
        commands_lookup,
        tasks_lookup,
        artifacts_lookup,
        relations_lookup,
    )
    response = build_meeting_execution_graph(
        workspace_id=workspace_id,
        meeting_id=meeting_id,
        commands=commands,
        tasks=tasks,
        artifacts=artifacts,
        relations=relations,
    )
    return merge_meeting_event_runtime_projection(response, events)
