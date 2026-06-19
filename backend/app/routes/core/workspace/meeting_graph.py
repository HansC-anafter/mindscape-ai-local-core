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
from backend.app.services.host_runtime_sessions.session_store import (
    HostRuntimeSessionStore,
)

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


async def _bounded_host_runtime_ledger_lookup(
    *,
    store: HostRuntimeSessionStore,
    workspace_id: str,
    meeting_id: str,
    session_limit: int = 8,
    event_limit: int = 80,
) -> tuple[List[Any], dict[str, List[Any]]]:
    sessions = await _bounded_graph_lookup(
        "host_runtime_sessions",
        lambda: store.list_sessions_by_meeting(
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            limit=session_limit,
        ),
        timeout=2.0,
    )
    event_lookups = [
        _bounded_graph_lookup(
            f"host_runtime_events:{session.id}",
            lambda session_id=session.id: store.list_events(
                workspace_id=workspace_id,
                session_id=session_id,
                limit=event_limit,
            ),
            timeout=2.0,
        )
        for session in sessions
        if getattr(session, "id", None)
    ]
    event_results = await asyncio.gather(*event_lookups) if event_lookups else []
    events_by_session: dict[str, List[Any]] = {}
    for session, events in zip(sessions, event_results):
        session_id = str(getattr(session, "id", "") or "")
        if session_id:
            events_by_session[session_id] = list(events or [])
    return sessions, events_by_session


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
    host_runtime_store = HostRuntimeSessionStore()

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
    host_runtime_ledger_lookup = _bounded_host_runtime_ledger_lookup(
        store=host_runtime_store,
        workspace_id=workspace_id,
        meeting_id=meeting_id,
    )
    (
        events,
        commands,
        tasks,
        artifacts,
        relations,
        host_runtime_ledger,
    ) = await asyncio.gather(
        events_lookup,
        commands_lookup,
        tasks_lookup,
        artifacts_lookup,
        relations_lookup,
        host_runtime_ledger_lookup,
    )
    host_runtime_sessions, host_runtime_events_by_session = host_runtime_ledger
    response = build_meeting_execution_graph(
        workspace_id=workspace_id,
        meeting_id=meeting_id,
        commands=commands,
        tasks=tasks,
        artifacts=artifacts,
        relations=relations,
        host_runtime_sessions=host_runtime_sessions,
        host_runtime_events_by_session=host_runtime_events_by_session,
    )
    return merge_meeting_event_runtime_projection(response, events)
