"""
Endpoints for workspace features that web-console hooks depend on.

These serve real data from Postgres stores (projects, events, threads, timeline).
Previously returning 404, causing the workspace page to fail loading.

Root cause: commit f4e83da9 decomposed page.tsx into hooks that call
/events, /threads, /timeline with strict error handling.
"""

import asyncio
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
async def get_workspace_events(
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
async def get_workspace_timeline(
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
async def list_workspace_projects(
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
async def get_workspace_project(
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
async def list_workspace_threads(
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


@router.get("/{workspace_id}/threads/{thread_id}/bundle")
async def get_thread_bundle(
    workspace_id: str = PathParam(...),
    thread_id: str = PathParam(...),
):
    """Return ThreadBundle for ThreadBundlePanel.tsx"""
    try:
        # Get thread info
        with store.events.get_connection() as conn:
            thread_row = conn.execute(
                text(
                    "SELECT * FROM conversation_threads "
                    "WHERE id = :tid AND workspace_id = :ws"
                ),
                {"tid": thread_id, "ws": workspace_id},
            ).fetchone()

        title = thread_row.title if thread_row else "Thread"
        project_id = (
            str(thread_row.project_id) if thread_row and thread_row.project_id else None
        )

        # Get thread references
        references = []
        try:
            with store.events.get_connection() as conn:
                ref_rows = conn.execute(
                    text(
                        "SELECT * FROM thread_references "
                        "WHERE thread_id = :tid ORDER BY created_at DESC LIMIT 20"
                    ),
                    {"tid": thread_id},
                ).fetchall()
            for ref in ref_rows:
                references.append(
                    {
                        "id": str(ref.id),
                        "source_type": getattr(ref, "source_type", "url"),
                        "uri": getattr(ref, "uri", ""),
                        "title": getattr(ref, "title", ""),
                        "snippet": getattr(ref, "snippet", None),
                        "reason": getattr(ref, "reason", None),
                        "created_at": (
                            str(ref.created_at)
                            if hasattr(ref, "created_at") and ref.created_at
                            else ""
                        ),
                        "pinned_by": getattr(ref, "pinned_by", "ai"),
                    }
                )
        except Exception:
            pass

        # Get runs (executions) related to this thread via meeting sessions
        runs = []
        try:
            from backend.app.services.stores.tasks_store import TasksStore

            tasks_store = TasksStore()
            # Find meeting sessions for this thread
            with store.events.get_connection() as conn:
                session_rows = conn.execute(
                    text(
                        "SELECT id FROM meeting_sessions "
                        "WHERE workspace_id = :ws AND thread_id = :tid "
                        "ORDER BY started_at DESC LIMIT 5"
                    ),
                    {"ws": workspace_id, "tid": thread_id},
                ).fetchall()
            seen_task_ids = set()
            for sr in session_rows:
                sid = sr.id if hasattr(sr, "id") else sr[0]
                session_tasks = tasks_store.list_tasks_by_meeting_session(str(sid))
                for t in session_tasks:
                    # Only show actual execution tasks, exclude planning items
                    if t.task_type not in (
                        "playbook_execution",
                        "tool_execution",
                    ):
                        continue
                    if t.id in seen_task_ids:
                        continue
                    seen_task_ids.add(t.id)
                    ctx = (
                        t.execution_context
                        if isinstance(t.execution_context, dict)
                        else {}
                    )
                    duration = None
                    if t.created_at and t.completed_at:
                        try:
                            duration = int(
                                (t.completed_at - t.created_at).total_seconds() * 1000
                            )
                        except Exception:
                            pass
                    runs.append(
                        {
                            "id": str(t.id),
                            "playbook_name": ctx.get("playbook_name", t.pack_id or ""),
                            "status": _map_status(
                                str(t.status) if t.status else "running"
                            ),
                            "started_at": (str(t.started_at or t.created_at or "")),
                            "duration_ms": duration,
                            "steps_completed": 0,
                            "steps_total": 0,
                            "deliverable_ids": [],
                            "result_summary": None,
                        }
                    )
        except Exception:
            pass

        # Get deliverables (artifacts linked to this thread)
        deliverables = []
        try:
            artifacts = store.artifacts.get_by_thread(workspace_id, thread_id, limit=20)
            for a in artifacts:
                deliverables.append(
                    {
                        "id": a.id,
                        "type": (
                            a.artifact_type.value
                            if hasattr(a.artifact_type, "value")
                            else str(a.artifact_type)
                        ),
                        "title": a.title,
                        "summary": a.summary,
                        "created_at": (
                            a.created_at.isoformat() if a.created_at else ""
                        ),
                    }
                )
        except Exception:
            pass

        # Derive status from meeting session
        bundle_status = "in_progress"
        try:
            with store.events.get_connection() as conn:
                ms_row = conn.execute(
                    text(
                        "SELECT status FROM meeting_sessions "
                        "WHERE workspace_id = :ws AND thread_id = :tid "
                        "ORDER BY started_at DESC LIMIT 1"
                    ),
                    {"ws": workspace_id, "tid": thread_id},
                ).fetchone()
            if ms_row:
                ms_status = ms_row.status if hasattr(ms_row, "status") else ms_row[0]
                if ms_status == "closed":
                    bundle_status = "completed"
                elif ms_status == "failed":
                    bundle_status = "failed"
        except Exception:
            pass

        return {
            "thread_id": thread_id,
            "overview": {
                "title": title,
                "brief": None,
                "status": bundle_status,
                "summary": None,
                "project_id": project_id,
                "labels": [],
                "pinned_scope": None,
            },
            "deliverables": deliverables,
            "references": references,
            "runs": runs,
            "sources": [],
        }
    except Exception as exc:
        logger.warning(f"Failed to build thread bundle for {thread_id}: {exc}")
        return {
            "thread_id": thread_id,
            "overview": {
                "title": "Thread",
                "status": "in_progress",
                "labels": [],
            },
            "deliverables": [],
            "references": [],
            "runs": [],
            "sources": [],
        }


def _map_status(status: str) -> str:
    """Map tasks.status to ThreadRun status values."""
    mapping = {
        "running": "running",
        "succeeded": "completed",
        "failed": "failed",
        "cancelled": "cancelled",
        "cancelled_by_user": "cancelled",
        "pending": "running",
    }
    return mapping.get(status, "running")
