"""
Workspace Timeline Routes

Handles /workspaces/{id}/events and /workspaces/{id}/timeline endpoints.
"""

import logging
import traceback
import sys
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Path, Query, Depends

from backend.app.routes.workspace_schemas import EventsListResponse, TimelineListResponse
from backend.app.routes.workspace_dependencies import get_workspace, get_store, get_timeline_items_store
from backend.app.models.workspace import Workspace
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.stores.timeline_items_store import TimelineItemsStore
from backend.app.services.stores.tasks_store import TasksStore

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces-timeline"])
logger = logging.getLogger(__name__)


@router.get("/{workspace_id}/events", response_model=EventsListResponse)
async def get_workspace_events(
    workspace_id: str = Path(..., description="Workspace ID"),
    start_time: Optional[str] = Query(None, description="Start time filter (ISO format)"),
    end_time: Optional[str] = Query(None, description="End time filter (ISO format)"),
    event_types: Optional[str] = Query(None, description="Comma-separated event types"),
    limit: int = Query(50, ge=1, le=1000, description="Maximum number of events"),
    before_id: Optional[str] = Query(None, description="Load events before this event ID (cursor-based pagination)"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store)
):
    """
    Get workspace events (MindEvent) for chat history

    Returns MindEvent objects for chat message display.
    This is the source of truth for chat messages (left panel).

    Supports cursor-based pagination using before_id parameter for efficient loading
    of older messages when scrolling up in chat.
    """
    try:
        start_dt = datetime.fromisoformat(start_time) if start_time else None
        end_dt = datetime.fromisoformat(end_time) if end_time else None

        recent_events = store.get_events_by_workspace(
            workspace_id=workspace_id,
            start_time=start_dt,
            end_time=end_dt,
            limit=limit,
            before_id=before_id
        )

        if event_types:
            type_list = [t.strip() for t in event_types.split(',')]
            recent_events = [
                event for event in recent_events
                if (event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type)) in type_list
            ]

        display_events_dicts = []
        for event in recent_events:
            payload = event.payload if isinstance(event.payload, dict) else {}
            entity_ids = event.entity_ids if isinstance(event.entity_ids, list) else []
            metadata = event.metadata if isinstance(event.metadata, dict) else {}

            event_dict = {
                'id': event.id,
                'timestamp': (event.timestamp.isoformat() + 'Z' if event.timestamp.tzinfo is None else event.timestamp.isoformat()) if event.timestamp else None,
                'actor': event.actor.value if hasattr(event.actor, 'value') else str(event.actor),
                'channel': event.channel,
                'profile_id': event.profile_id,
                'project_id': event.project_id,
                'workspace_id': event.workspace_id,
                'event_type': event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type),
                'payload': payload,
                'entity_ids': entity_ids,
                'metadata': metadata
            }
            display_events_dicts.append(event_dict)

        has_more = len(recent_events) >= limit and len(display_events_dicts) >= limit

        return EventsListResponse(
            workspace_id=workspace_id,
            total=len(display_events_dicts),
            events=display_events_dicts,
            has_more=has_more
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get workspace events: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to get workspace events: {str(e)}")


@router.get("/{workspace_id}/timeline", response_model=TimelineListResponse)
async def get_workspace_timeline(
    workspace_id: str = Path(..., description="Workspace ID"),
    start_time: Optional[str] = Query(None, description="Start time filter (ISO format)"),
    end_time: Optional[str] = Query(None, description="End time filter (ISO format)"),
    event_types: Optional[str] = Query(None, description="Comma-separated event types"),
    limit: int = Query(200, ge=1, le=1000, description="Maximum number of events"),
    workspace: Workspace = Depends(get_workspace),
    timeline_items_store: TimelineItemsStore = Depends(get_timeline_items_store),
    store: MindscapeStore = Depends(get_store)
):
    """
    Get workspace timeline items

    Returns timeline items from timeline_items table (single source of truth).
    Timeline items represent Pack execution results displayed in the right panel.
    """
    try:
        timeline_items = timeline_items_store.list_timeline_items_by_workspace(
            workspace_id=workspace_id,
            limit=limit
        )

        if start_time or end_time:
            start = datetime.fromisoformat(start_time) if start_time else None
            end = datetime.fromisoformat(end_time) if end_time else None

            filtered_items = []
            for item in timeline_items:
                item_time = item.created_at
                if start and item_time < start:
                    continue
                if end and item_time > end:
                    continue
                filtered_items.append(item)
            timeline_items = filtered_items

        if event_types:
            type_list = [t.strip() for t in event_types.split(',')]
            timeline_items = [item for item in timeline_items if item.type.value in type_list]

        # Load TasksStore to check for execution_context
        tasks_store = TasksStore(db_path=store.db_path)

        enriched_items = []
        for item in timeline_items:
            enriched = {
                'id': item.id,
                'workspace_id': item.workspace_id,
                'message_id': item.message_id,
                'task_id': item.task_id,
                'type': item.type.value,
                'title': item.title,
                'summary': item.summary,
                'data': item.data,
                'cta': item.cta,
                'created_at': (item.created_at.isoformat() + 'Z' if item.created_at.tzinfo is None else item.created_at.isoformat()) if item.created_at else None
            }

            # Check if timeline item is associated with a Playbook execution task
            if item.task_id:
                try:
                    task = tasks_store.get_task(item.task_id)
                    if task and task.execution_context:
                        # This timeline item is from a Playbook execution
                        enriched['execution_id'] = task.execution_id or task.id
                        enriched['task_status'] = task.status.value if task.status else None
                        enriched['task_started_at'] = task.started_at.isoformat() if task.started_at else None
                        enriched['task_completed_at'] = task.completed_at.isoformat() if task.completed_at else None
                        enriched['has_execution_context'] = True
                    else:
                        enriched['has_execution_context'] = False
                except Exception as e:
                    logger.warning(f"Failed to load task {item.task_id} for timeline item {item.id}: {e}")
                    enriched['has_execution_context'] = False
            else:
                enriched['has_execution_context'] = False

            enriched_items.append(enriched)

        logger.info(f"Returning {len(enriched_items)} timeline items for workspace {workspace_id}")

        return TimelineListResponse(
            workspace_id=workspace_id,
            total=len(enriched_items),
            timeline_items=enriched_items,
            events=enriched_items
        )
    except HTTPException:
        raise
    except Exception as e:
        full_traceback = ''.join(traceback.format_exception(*sys.exc_info()))
        logger.error(f"Timeline error: {str(e)}\n{full_traceback}")
        print(f"ERROR: Timeline error: {str(e)}", file=sys.stderr)
        print(full_traceback, file=sys.stderr)
        raise
