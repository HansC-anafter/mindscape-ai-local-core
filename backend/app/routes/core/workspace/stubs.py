"""
Endpoints for workspace features that web-console hooks depend on.

These serve real data from Postgres stores (projects, events, threads, timeline).
Previously returning 404, causing the workspace page to fail loading.

Root cause: commit f4e83da9 decomposed page.tsx into hooks that call
/events, /threads, /timeline with strict error handling.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Path as PathParam, Query
from sqlalchemy import text
from starlette.responses import StreamingResponse

from ....services.mindscape_store import MindscapeStore

logger = logging.getLogger(__name__)
router = APIRouter()
store = MindscapeStore()


# ---------------------------------------------------------------------------
# Events  (chat history, execution plan events, decision events)
# Called by: useChatEvents.ts, useExecutionState.ts
# ---------------------------------------------------------------------------
@router.get("/{workspace_id}/events")
def get_workspace_events(
    workspace_id: str = PathParam(...),
    event_types: Optional[str] = Query(None),
    limit: int = Query(200),
    _t: Optional[str] = Query(None),
    thread_id: Optional[str] = Query(None),
):
    try:
        # Build query with event_type filtering at SQL level
        query_str = "SELECT * FROM mind_events WHERE workspace_id = :ws"
        params: dict = {"ws": workspace_id, "lim": limit}

        if thread_id:
            query_str += " AND thread_id = :tid"
            params["tid"] = thread_id

        if event_types:
            type_list = [t.strip() for t in event_types.split(",") if t.strip()]
            if type_list:
                placeholders = ", ".join(f":et{i}" for i in range(len(type_list)))
                query_str += f" AND event_type IN ({placeholders})"
                for i, et in enumerate(type_list):
                    params[f"et{i}"] = et

        query_str += " ORDER BY timestamp DESC, id DESC LIMIT :lim"

        with store.events.get_connection() as conn:
            rows = conn.execute(text(query_str), params).fetchall()

        events = [store.events._row_to_event(r).model_dump() for r in rows]
        return {"events": events, "has_more": len(events) >= limit}
    except Exception as exc:
        logger.warning(f"Failed to load events for workspace {workspace_id}: {exc}")
        return {"events": [], "has_more": False}


# NOTE: SSE streaming endpoint has been moved to features/workspace/timeline.py
# (event_stream_generator) which actually polls DB for new events.
# The stub here was shadowing the real implementation, preventing real-time updates.


# ---------------------------------------------------------------------------
# Timeline
# Called by: TimelinePanel.tsx
# ---------------------------------------------------------------------------
@router.get("/{workspace_id}/timeline")
def get_workspace_timeline(
    workspace_id: str = PathParam(...),
    limit: int = Query(50),
):
    try:
        events = store.events.get_timeline(
            profile_id="default-user",
            workspace_id=workspace_id,
            limit=limit,
        )
        return {"items": [e.model_dump() for e in events], "total": len(events)}
    except Exception as exc:
        logger.warning(f"Failed to load timeline for workspace {workspace_id}: {exc}")
        return {"items": [], "total": 0}


# ---------------------------------------------------------------------------
# Projects
# Called by: useWorkspaceProjects.ts, page.tsx, ProjectCard.tsx
# ---------------------------------------------------------------------------
@router.get("/{workspace_id}/projects")
def list_workspace_projects(
    workspace_id: str = PathParam(...),
    state: Optional[str] = Query(None),
    limit: int = Query(20),
    project_type: Optional[str] = Query(None),
):
    try:
        projects = store.projects.list_projects(
            workspace_id=workspace_id,
            state=state,
            project_type=project_type,
            limit=limit,
        )
        return {"projects": [p.model_dump() for p in projects]}
    except Exception as exc:
        logger.warning(f"Failed to list projects for workspace {workspace_id}: {exc}")
        return {"projects": []}


@router.get("/{workspace_id}/projects/{project_id}")
def get_workspace_project(
    workspace_id: str = PathParam(...),
    project_id: str = PathParam(...),
):
    try:
        project = store.projects.get_project(project_id)
        if project:
            return project.model_dump()
        return {"id": project_id, "title": project_id, "state": "unknown"}
    except Exception as exc:
        logger.warning(f"Failed to get project {project_id}: {exc}")
        return {"id": project_id, "title": project_id, "state": "unknown"}


# ---------------------------------------------------------------------------
# Threads (conversations list)
# Called by: ConversationsList.tsx
# ConversationsList.tsx line 55: setThreads(data || []) — expects raw array
# ---------------------------------------------------------------------------
@router.get("/{workspace_id}/threads")
def list_workspace_threads(
    workspace_id: str = PathParam(...),
    limit: int = Query(50),
):
    try:
        # conversation_threads table is in Postgres, query directly
        with store.events.get_connection() as conn:
            rows = conn.execute(
                text(
                    "SELECT * FROM conversation_threads "
                    "WHERE workspace_id = :ws "
                    "ORDER BY updated_at DESC LIMIT :lim"
                ),
                {"ws": workspace_id, "lim": limit},
            ).fetchall()

        threads = []
        for r in rows:
            threads.append(
                {
                    "id": str(r.id),
                    "workspace_id": str(r.workspace_id),
                    "title": r.title or "",
                    "project_id": str(r.project_id) if r.project_id else None,
                    "pinned_scope": (
                        r.pinned_scope if hasattr(r, "pinned_scope") else None
                    ),
                    "created_at": str(r.created_at) if r.created_at else None,
                    "updated_at": str(r.updated_at) if r.updated_at else None,
                    "last_message_at": (
                        str(r.last_message_at)
                        if hasattr(r, "last_message_at") and r.last_message_at
                        else str(r.updated_at)
                    ),
                    "message_count": (
                        r.message_count if hasattr(r, "message_count") else 0
                    ),
                    "metadata": {},
                    "is_default": (
                        bool(r.is_default) if hasattr(r, "is_default") else False
                    ),
                }
            )
        return threads
    except Exception as exc:
        logger.warning(f"Failed to list threads for workspace {workspace_id}: {exc}")
        return []




