"""
Stub endpoints for workspace features referenced by web-console hooks
(useChatEvents, ConversationsList, TimelinePanel, useWorkspaceProjects)
that call cloud-only endpoints not yet implemented in local-core.

Returning well-formed empty responses prevents the workspace page from
showing "載入工作空間失敗" due to 404 retry loops.

Root cause: commit f4e83da9 decomposed page.tsx into hooks that call
/events, /threads, /timeline with strict error handling.  These routes
never existed in local-core backend.
"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Path as PathParam, Query
from starlette.responses import StreamingResponse

logger = logging.getLogger(__name__)
router = APIRouter()


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
    return {"events": [], "total": 0}


@router.get("/{workspace_id}/events/stream")
async def stream_workspace_events(
    workspace_id: str = PathParam(...),
    event_types: Optional[str] = Query(None),
):
    """SSE stub: immediately sends stream_end so the client stops reconnecting."""

    async def _gen():
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
    return {"items": [], "total": 0}


# ---------------------------------------------------------------------------
# Projects
# Called by: useWorkspaceProjects.ts, page.tsx
# ---------------------------------------------------------------------------
@router.get("/{workspace_id}/projects")
async def list_workspace_projects(
    workspace_id: str = PathParam(...),
    state: Optional[str] = Query(None),
    limit: int = Query(20),
    project_type: Optional[str] = Query(None),
):
    return {"projects": []}


@router.get("/{workspace_id}/projects/{project_id}")
async def get_workspace_project(
    workspace_id: str = PathParam(...),
    project_id: str = PathParam(...),
):
    return {
        "id": project_id,
        "workspace_id": workspace_id,
        "title": project_id,
        "state": "open",
        "created_at": None,
    }


# ---------------------------------------------------------------------------
# Threads (conversations list)
# Called by: ConversationsList.tsx
# ---------------------------------------------------------------------------
@router.get("/{workspace_id}/threads")
async def list_workspace_threads(
    workspace_id: str = PathParam(...),
    limit: int = Query(50),
):
    return {"threads": [], "total": 0}
