"""
Workspace timeline routes.

This module keeps the public workspace events, timeline, and SSE route paths.
Implementation details live in timeline_core helpers.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fastapi.responses import StreamingResponse

from backend.app.models.workspace import Workspace
from backend.app.routes.workspace_dependencies import (
    get_store,
    get_timeline_items_store,
    get_workspace,
)
from backend.app.routes.workspace_schemas import EventsListResponse, TimelineListResponse
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.stores.timeline_items_store import TimelineItemsStore
from backend.features.workspace.timeline_core.events import build_workspace_events_response
from backend.features.workspace.timeline_core.items import build_workspace_timeline_response
from backend.features.workspace.timeline_core.stream import event_stream_generator

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces-timeline"])
logger = logging.getLogger(__name__)


@router.get("/{workspace_id}/events", response_model=EventsListResponse)
async def get_workspace_events(
    workspace_id: str = Path(..., description="Workspace ID"),
    thread_id: Optional[str] = Query(
        None, description="Filter by conversation thread ID"
    ),
    start_time: Optional[str] = Query(
        None, description="Start time filter (ISO format)"
    ),
    end_time: Optional[str] = Query(None, description="End time filter (ISO format)"),
    event_types: Optional[str] = Query(None, description="Comma-separated event types"),
    limit: int = Query(50, ge=1, le=1000, description="Maximum number of events"),
    before_id: Optional[str] = Query(
        None, description="Load events before this event ID (cursor-based pagination)"
    ),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store),
):
    """
    Get workspace events for chat history.

    Returns MindEvent objects for chat message display. This endpoint supports
    cursor-based pagination through before_id and optional thread filtering.
    """
    return await build_workspace_events_response(
        workspace_id=workspace_id,
        thread_id=thread_id,
        start_time=start_time,
        end_time=end_time,
        event_types=event_types,
        limit=limit,
        before_id=before_id,
        workspace=workspace,
        store=store,
    )


@router.get("/{workspace_id}/timeline", response_model=TimelineListResponse)
async def get_workspace_timeline(
    workspace_id: str = Path(..., description="Workspace ID"),
    start_time: Optional[str] = Query(
        None, description="Start time filter (ISO format)"
    ),
    end_time: Optional[str] = Query(None, description="End time filter (ISO format)"),
    event_types: Optional[str] = Query(None, description="Comma-separated event types"),
    limit: int = Query(200, ge=1, le=1000, description="Maximum number of events"),
    workspace: Workspace = Depends(get_workspace),
    timeline_items_store: TimelineItemsStore = Depends(get_timeline_items_store),
    store: MindscapeStore = Depends(get_store),
):
    """
    Get workspace timeline items.

    Returns timeline items from the timeline_items table.
    """
    return await build_workspace_timeline_response(
        workspace_id=workspace_id,
        start_time=start_time,
        end_time=end_time,
        event_types=event_types,
        limit=limit,
        timeline_items_store=timeline_items_store,
        store=store,
    )


@router.get("/{workspace_id}/events/stream")
async def stream_workspace_events(
    request: Request,
    workspace_id: str = Path(..., description="Workspace ID"),
    event_types: Optional[str] = Query(
        None, description="Comma-separated list of event types to filter"
    ),
    project_id: Optional[str] = Query(
        None, description="Optional project ID to filter"
    ),
    start_time: Optional[str] = Query(
        None, description="Start time filter (ISO format)"
    ),
    last_event_id: Optional[str] = Query(
        None, description="Last event ID to resume from"
    ),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store),
):
    """
    Stream unified events for a workspace through SSE.
    """
    try:
        event_type_list = None
        if event_types:
            event_type_list = [et.strip() for et in event_types.split(",")]

        start_time_dt = None
        if start_time:
            try:
                start_time_dt = datetime.fromisoformat(
                    start_time.replace("Z", "+00:00")
                )
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid start_time format. Use ISO 8601 format.",
                )

        return StreamingResponse(
            event_stream_generator(
                workspace_id=workspace_id,
                store=store,
                event_types=event_type_list,
                project_id=project_id,
                start_time=start_time_dt,
                last_event_id=last_event_id,
                client_disconnected=request.is_disconnected,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "Content-Type": "text/event-stream; charset=utf-8",
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to stream events: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to stream events: {str(e)}"
        )
