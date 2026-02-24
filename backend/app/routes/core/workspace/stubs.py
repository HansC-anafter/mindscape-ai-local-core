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
):
    try:
        # Build query with event_type filtering at SQL level
        query_str = "SELECT * FROM mind_events WHERE workspace_id = :ws"
        params: dict = {"ws": workspace_id, "lim": limit}

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


@router.get("/{workspace_id}/events/stream")
async def stream_workspace_events(
    workspace_id: str = PathParam(...),
    event_types: Optional[str] = Query(None),
):
    """SSE endpoint: sends keepalive pings to prevent client reconnection loops."""

    async def _gen():
        # Send initial connected event
        yield f"data: {json.dumps({'type': 'connected'})}\n\n"
        # Keep connection alive with periodic pings (every 15s, up to 5 min)
        for _ in range(20):
            await asyncio.sleep(15)
            yield f": ping\n\n"
        # After 5 min, close gracefully — client will reconnect once
        yield f"data: {json.dumps({'type': 'stream_end'})}\n\n"

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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


# /card must be registered BEFORE the generic /{project_id} route
@router.get("/{workspace_id}/projects/{project_id}/card")
async def get_project_card(
    workspace_id: str = PathParam(...),
    project_id: str = PathParam(...),
):
    """Return ProjectCardData for ProjectCard.tsx"""
    try:
        project = store.projects.get_project(project_id)
        title = project.title if project else project_id

        # Query execution stats from tasks table
        with store.events.get_connection() as conn:
            stats_row = conn.execute(
                text(
                    """
                    SELECT
                        COUNT(*) FILTER (WHERE status = 'running') AS running,
                        COUNT(*) FILTER (WHERE status = 'succeeded') AS completed,
                        COUNT(*) FILTER (WHERE status = 'pending') AS pending,
                        COUNT(*) AS total
                    FROM tasks
                    WHERE workspace_id = :ws
                """
                ),
                {"ws": workspace_id},
            ).fetchone()

        running = stats_row.running if stats_row else 0
        completed = stats_row.completed if stats_row else 0
        pending = stats_row.pending if stats_row else 0
        total = stats_row.total if stats_row else 0

        # Get recent relevant events for this project
        recent_events = []
        try:
            with store.events.get_connection() as conn:
                event_rows = conn.execute(
                    text(
                        """
                        SELECT id, event_type, payload, timestamp, metadata
                        FROM mind_events
                        WHERE workspace_id = :ws
                          AND event_type IN ('playbook_step', 'step_completed',
                                             'artifact_created', 'run_started')
                        ORDER BY timestamp DESC
                        LIMIT 10
                    """
                    ),
                    {"ws": workspace_id},
                ).fetchall()

            for er in event_rows:
                payload = er.payload if isinstance(er.payload, dict) else {}
                meta = er.metadata if isinstance(er.metadata, dict) else {}
                recent_events.append(
                    {
                        "id": str(er.id),
                        "type": "step_completed",
                        "playbookCode": payload.get("playbook_code", ""),
                        "playbookName": payload.get(
                            "playbook_name", meta.get("playbook_code", "")
                        ),
                        "executionId": payload.get(
                            "execution_id", meta.get("execution_id", "")
                        ),
                        "stepIndex": payload.get("step_index"),
                        "stepName": payload.get("step_name", ""),
                        "timestamp": str(er.timestamp) if er.timestamp else "",
                        "projectId": project_id,
                    }
                )
        except Exception:
            pass

        # Meeting state
        meeting_enabled = bool(
            project and project.metadata and project.metadata.get("meeting_enabled")
        )
        meeting_info = {
            "enabled": meeting_enabled,
            "active": False,
            "session_id": None,
            "status": None,
            "round_count": 0,
            "max_rounds": 5,
            "action_item_count": 0,
            "last_activity": None,
            "minutes_preview": "",
        }

        # Try to get active meeting session
        if meeting_enabled:
            try:
                with store.events.get_connection() as conn:
                    ms_row = conn.execute(
                        text(
                            """
                            SELECT id, status, round_count, max_rounds,
                                   action_item_count, updated_at
                            FROM meeting_sessions
                            WHERE project_id = :pid
                              AND status IN ('active', 'paused')
                            ORDER BY updated_at DESC LIMIT 1
                        """
                        ),
                        {"pid": project_id},
                    ).fetchone()
                if ms_row:
                    meeting_info.update(
                        {
                            "active": ms_row.status == "active",
                            "session_id": str(ms_row.id),
                            "status": ms_row.status,
                            "round_count": ms_row.round_count or 0,
                            "max_rounds": ms_row.max_rounds or 5,
                            "action_item_count": ms_row.action_item_count or 0,
                            "last_activity": (
                                str(ms_row.updated_at) if ms_row.updated_at else None
                            ),
                        }
                    )
            except Exception:
                pass

        progress_pct = min(int((completed / max(total, 1)) * 100), 100) if total else 0

        return {
            "projectId": project_id,
            "projectName": title,
            "status": (
                "active"
                if running > 0
                else ("completed" if completed > 0 else "active")
            ),
            "lastActivity": (
                str(project.updated_at) if project and project.updated_at else ""
            ),
            "stats": {
                "totalPlaybooks": total,
                "runningExecutions": running,
                "pendingConfirmations": pending,
                "completedExecutions": completed,
                "artifactCount": 0,
            },
            "progress": {
                "current": progress_pct,
                "label": f"{completed}/{total} completed" if total else "No executions",
            },
            "recentEvents": recent_events[:5],
            "playbooks": [],
            "meeting": meeting_info,
        }
    except Exception as exc:
        logger.warning(f"Failed to build project card for {project_id}: {exc}")
        return {
            "projectId": project_id,
            "projectName": project_id,
            "status": "active",
            "lastActivity": "",
            "stats": {
                "totalPlaybooks": 0,
                "runningExecutions": 0,
                "pendingConfirmations": 0,
                "completedExecutions": 0,
                "artifactCount": 0,
            },
            "progress": {"current": 0, "label": ""},
            "recentEvents": [],
            "playbooks": [],
            "meeting": {"enabled": False, "active": False},
        }


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
