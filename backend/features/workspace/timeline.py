"""
Workspace Timeline Routes

Handles /workspaces/{id}/events and /workspaces/{id}/timeline endpoints.
Also provides SSE streaming for unified event stream (ReAct/ToT loop visualization).
"""

import logging
import traceback
import sys
import json
import asyncio
from datetime import datetime, timezone
from typing import Optional, AsyncGenerator, List
from fastapi import APIRouter, HTTPException, Path, Query, Depends
from fastapi.responses import StreamingResponse

from backend.app.routes.workspace_schemas import (
    EventsListResponse,
    TimelineListResponse,
)
from backend.app.routes.workspace_dependencies import (
    get_workspace,
    get_store,
    get_timeline_items_store,
)
from backend.app.models.workspace import Workspace
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.stores.timeline_items_store import TimelineItemsStore
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.models.mindscape import EventType

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
    Get workspace events (MindEvent) for chat history

    Returns MindEvent objects for chat message display.
    This is the source of truth for chat messages (left panel).

    Supports cursor-based pagination using before_id parameter for efficient loading
    of older messages when scrolling up in chat.

    If thread_id is provided, only returns events for that conversation thread.
    If thread_id is not provided, returns all events (backward compatible).
    """
    try:
        start_dt = datetime.fromisoformat(start_time) if start_time else None
        end_dt = datetime.fromisoformat(end_time) if end_time else None

        if thread_id:
            # Filter by thread_id
            recent_events = await asyncio.to_thread(
                store.events.get_events_by_thread,
                workspace_id=workspace_id,
                thread_id=thread_id,
                start_time=start_dt,
                end_time=end_dt,
                limit=limit,
                before_id=before_id,
            )
        else:
            # Backward compatible: get all events
            recent_events = await asyncio.to_thread(
                store.get_events_by_workspace,
                workspace_id=workspace_id,
                start_time=start_dt,
                end_time=end_dt,
                limit=limit,
                before_id=before_id,
            )

        # Check if workspace has welcome message (cold start check)
        # Only check if no before_id (initial load) and no event_types filter
        if not before_id and not event_types:
            has_welcome = False
            for event in recent_events:
                payload = event.payload if isinstance(event.payload, dict) else {}
                metadata = event.metadata if isinstance(event.metadata, dict) else {}
                if payload.get("is_welcome") or metadata.get("is_cold_start"):
                    has_welcome = True
                    break

            # If no welcome message found, generate one
            if not has_welcome:
                try:
                    from backend.app.services.workspace_welcome_service import (
                        WorkspaceWelcomeService,
                    )
                    from backend.app.models.mindscape import (
                        MindEvent,
                        EventType,
                        EventActor,
                    )
                    import uuid

                    locale = (
                        workspace.default_locale
                        if hasattr(workspace, "default_locale")
                        and workspace.default_locale
                        else "zh-TW"
                    )
                    welcome_message, suggestions = (
                        await WorkspaceWelcomeService.generate_welcome_message(
                            workspace, workspace.owner_user_id, store, locale=locale
                        )
                    )

                    if welcome_message:
                        # If this request is scoped to a thread, write welcome into that thread.
                        # Otherwise, fall back to (get or create) the default thread.
                        target_thread_id = thread_id
                        if not target_thread_id:
                            from backend.features.workspace.chat.streaming.generator import (
                                _get_or_create_default_thread,
                            )

                            target_thread_id = _get_or_create_default_thread(
                                workspace_id, store
                            )

                        welcome_event = MindEvent(
                            id=str(uuid.uuid4()),
                            timestamp=datetime.now(timezone.utc),
                            actor=EventActor.ASSISTANT,
                            channel="local_workspace",
                            profile_id=workspace.owner_user_id,
                            project_id=workspace.primary_project_id,
                            workspace_id=workspace_id,
                            thread_id=target_thread_id,
                            event_type=EventType.MESSAGE,
                            payload={
                                "message": welcome_message,
                                "is_welcome": True,
                                "suggestions": suggestions,
                            },
                            entity_ids=[],
                            metadata={"is_cold_start": True},
                        )
                        await asyncio.to_thread(store.create_event, welcome_event)

                        # Update thread statistics (best effort)
                        try:
                            # Use COUNT query to accurately calculate message count
                            message_count = await asyncio.to_thread(
                                store.events.count_messages_by_thread,
                                workspace_id=workspace_id,
                                thread_id=target_thread_id,
                            )
                            await asyncio.to_thread(
                                store.conversation_threads.update_thread,
                                thread_id=target_thread_id,
                                last_message_at=datetime.now(timezone.utc),
                                message_count=message_count,
                            )
                        except Exception as e:
                            logger.warning(
                                f"Failed to update thread statistics for welcome message: {e}"
                            )

                        # Reload events to include the new welcome message (respect thread filter)
                        if thread_id:
                            recent_events = await asyncio.to_thread(
                                store.events.get_events_by_thread,
                                workspace_id=workspace_id,
                                thread_id=thread_id,
                                start_time=start_dt,
                                end_time=end_dt,
                                limit=limit,
                                before_id=before_id,
                            )
                        else:
                            recent_events = await asyncio.to_thread(
                                store.get_events_by_workspace,
                                workspace_id=workspace_id,
                                start_time=start_dt,
                                end_time=end_dt,
                                limit=limit,
                                before_id=before_id,
                            )
                        logger.info(
                            f"Generated cold start welcome message for workspace {workspace_id}"
                        )
                except Exception as e:
                    logger.warning(
                        f"Failed to generate welcome message for workspace {workspace_id}: {e}"
                    )

        if event_types:
            type_list = [t.strip() for t in event_types.split(",")]
            recent_events = [
                event
                for event in recent_events
                if (
                    event.event_type.value
                    if hasattr(event.event_type, "value")
                    else str(event.event_type)
                )
                in type_list
            ]

        display_events_dicts = []
        for event in recent_events:
            payload = event.payload if isinstance(event.payload, dict) else {}
            entity_ids = event.entity_ids if isinstance(event.entity_ids, list) else []
            metadata = event.metadata if isinstance(event.metadata, dict) else {}

            event_dict = {
                "id": event.id,
                "timestamp": (
                    (
                        event.timestamp.isoformat() + "Z"
                        if event.timestamp.tzinfo is None
                        else event.timestamp.isoformat()
                    )
                    if event.timestamp
                    else None
                ),
                "actor": (
                    event.actor.value
                    if hasattr(event.actor, "value")
                    else str(event.actor)
                ),
                "channel": event.channel,
                "profile_id": event.profile_id,
                "project_id": event.project_id,
                "workspace_id": event.workspace_id,
                "thread_id": event.thread_id,
                "event_type": (
                    event.event_type.value
                    if hasattr(event.event_type, "value")
                    else str(event.event_type)
                ),
                "payload": payload,
                "entity_ids": entity_ids,
                "metadata": metadata,
            }
            display_events_dicts.append(event_dict)

        has_more = len(recent_events) >= limit and len(display_events_dicts) >= limit

        return EventsListResponse(
            workspace_id=workspace_id,
            total=len(display_events_dicts),
            events=display_events_dicts,
            has_more=has_more,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to get workspace events: {str(e)}\n{traceback.format_exc()}"
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to get workspace events: {str(e)}"
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
    Get workspace timeline items

    Returns timeline items from timeline_items table (single source of truth).
    Timeline items represent Pack execution results displayed in the right panel.
    """
    try:
        timeline_items = await asyncio.to_thread(
            timeline_items_store.list_timeline_items_by_workspace,
            workspace_id=workspace_id,
            limit=limit,
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
            type_list = [t.strip() for t in event_types.split(",")]
            timeline_items = [
                item for item in timeline_items if item.type.value in type_list
            ]

        # Load TasksStore to check for execution_context
        tasks_store = TasksStore(db_path=store.db_path)

        enriched_items = []
        for item in timeline_items:
            enriched = {
                "id": item.id,
                "workspace_id": item.workspace_id,
                "message_id": item.message_id,
                "task_id": item.task_id,
                "type": item.type.value,
                "title": item.title,
                "summary": item.summary,
                "data": item.data,
                "cta": item.cta,
                "created_at": (
                    (
                        item.created_at.isoformat() + "Z"
                        if item.created_at.tzinfo is None
                        else item.created_at.isoformat()
                    )
                    if item.created_at
                    else None
                ),
            }

            # Check if timeline item is associated with a Playbook execution task
            if item.task_id:
                try:
                    task = await asyncio.to_thread(tasks_store.get_task, item.task_id)
                    if task and task.execution_context:
                        # This timeline item is from a Playbook execution
                        enriched["execution_id"] = task.execution_id or task.id
                        enriched["task_status"] = (
                            task.status.value if task.status else None
                        )
                        enriched["task_started_at"] = (
                            task.started_at.isoformat() if task.started_at else None
                        )
                        enriched["task_completed_at"] = (
                            task.completed_at.isoformat() if task.completed_at else None
                        )
                        enriched["has_execution_context"] = True
                    else:
                        enriched["has_execution_context"] = False
                except Exception as e:
                    logger.warning(
                        f"Failed to load task {item.task_id} for timeline item {item.id}: {e}"
                    )
                    enriched["has_execution_context"] = False
            else:
                enriched["has_execution_context"] = False

            enriched_items.append(enriched)

        logger.info(
            f"Returning {len(enriched_items)} timeline items for workspace {workspace_id}"
        )

        return TimelineListResponse(
            workspace_id=workspace_id,
            total=len(enriched_items),
            timeline_items=enriched_items,
            events=enriched_items,
        )
    except HTTPException:
        raise
    except Exception as e:
        full_traceback = "".join(traceback.format_exception(*sys.exc_info()))
        logger.error(f"Timeline error: {str(e)}\n{full_traceback}")
        print(f"ERROR: Timeline error: {str(e)}", file=sys.stderr)
        print(full_traceback, file=sys.stderr)
        raise


async def event_stream_generator(
    workspace_id: str,
    store: MindscapeStore,
    event_types: Optional[List[str]] = None,
    project_id: Optional[str] = None,
    start_time: Optional[datetime] = None,
    last_event_id: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """
    Generate SSE event stream for unified events (ReAct/ToT loop visualization)

    Events are projected to UI:
    - Right panel: DECISION_REQUIRED events → blocker cards
    - Left panel: RUN_STATE_CHANGED, ARTIFACT_CREATED events → progress
    - Center panel: All events → timeline

    Args:
        workspace_id: Workspace ID
        store: MindscapeStore instance
        event_types: Optional list of event types to filter
        project_id: Optional project ID to filter
        start_time: Optional start time to filter
        last_event_id: Optional last event ID to resume from
    """
    try:
        # Send initial connection message
        yield f"data: {json.dumps({'type': 'connected', 'workspace_id': workspace_id})}\n\n"

        # Convert event_types to EventType enum if provided
        event_type_enums = None
        if event_types:
            try:
                event_type_enums = [EventType(et) for et in event_types]
            except ValueError as e:
                logger.warning(f"Invalid event type in filter: {e}")

        # Poll for new events using timestamp-based filtering
        # Track the latest event timestamp we've seen
        last_poll_time = start_time or datetime.utcnow()
        seen_event_ids = set()

        # If resuming from last_event_id, load that event to get its timestamp
        if last_event_id:
            # Load events to find the last_event_id and get its timestamp
            resume_events = await asyncio.to_thread(
                store.get_events_by_workspace,
                workspace_id=workspace_id,
                start_time=None,
                limit=1000,
            )
            for event in resume_events:
                if event.id == last_event_id:
                    # Found the resume point - set last_poll_time to this event's timestamp
                    if isinstance(event.timestamp, datetime):
                        last_poll_time = event.timestamp
                    seen_event_ids.add(event.id)
                    break
                seen_event_ids.add(event.id)

        # Heartbeat counter to send keepalive messages
        heartbeat_counter = 0
        HEARTBEAT_INTERVAL = 30  # Send heartbeat every 30 seconds

        while True:
            try:
                # Query for new events using get_events_by_workspace
                # Get events after last_poll_time
                events = await asyncio.to_thread(
                    store.get_events_by_workspace,
                    workspace_id=workspace_id,
                    start_time=last_poll_time,
                    limit=100,
                )

                # Filter by event types if provided
                if event_type_enums:
                    events = [e for e in events if e.event_type in event_type_enums]

                # Filter by project_id if provided
                if project_id:
                    events = [e for e in events if e.project_id == project_id]

                # Send new events (only those we haven't seen)
                new_events = [e for e in events if e.id not in seen_event_ids]

                # Sort by timestamp ascending to process in chronological order
                new_events.sort(
                    key=lambda e: (
                        e.timestamp
                        if isinstance(e.timestamp, datetime)
                        else datetime.min
                    )
                )

                for event in new_events:
                    seen_event_ids.add(event.id)

                    # Format event for SSE
                    payload = event.payload if isinstance(event.payload, dict) else {}
                    entity_ids = (
                        event.entity_ids if isinstance(event.entity_ids, list) else []
                    )
                    metadata = (
                        event.metadata if isinstance(event.metadata, dict) else {}
                    )

                    event_data = {
                        "id": event.id,
                        "type": (
                            event.event_type.value
                            if hasattr(event.event_type, "value")
                            else str(event.event_type)
                        ),
                        "timestamp": (
                            (
                                event.timestamp.isoformat() + "Z"
                                if event.timestamp.tzinfo is None
                                else event.timestamp.isoformat()
                            )
                            if event.timestamp
                            else None
                        ),
                        "actor": (
                            event.actor.value
                            if hasattr(event.actor, "value")
                            else str(event.actor)
                        ),
                        "workspace_id": event.workspace_id,
                        "project_id": event.project_id,
                        "profile_id": event.profile_id,
                        "payload": payload,
                        "entity_ids": entity_ids,
                        "metadata": metadata,
                    }

                    # Send SSE formatted event
                    yield f"id: {event.id}\n"
                    yield f"event: {event_data['type']}\n"
                    yield f"data: {json.dumps(event_data)}\n\n"

                    # Update last_poll_time to this event's timestamp
                    if isinstance(event.timestamp, datetime):
                        last_poll_time = event.timestamp

                # Send heartbeat to keep connection alive
                heartbeat_counter += 1
                if heartbeat_counter >= HEARTBEAT_INTERVAL:
                    yield f": heartbeat\n\n"  # SSE comment line (keeps connection alive)
                    heartbeat_counter = 0

                # Wait before next poll
                await asyncio.sleep(1)  # Poll every 1 second

            except Exception as e:
                logger.error(f"Error in event stream: {e}", exc_info=True)
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
                await asyncio.sleep(5)  # Wait longer on error

    except Exception as e:
        logger.error(f"Fatal error in event stream: {e}", exc_info=True)
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"


@router.get("/{workspace_id}/events/stream")
async def stream_workspace_events(
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
    Stream unified events for a workspace (SSE)

    Events are projected to UI:
    - Right panel: DECISION_REQUIRED events → blocker cards
    - Left panel: RUN_STATE_CHANGED, ARTIFACT_CREATED events → progress
    - Center panel: All events → timeline

    Query Parameters:
    - event_types: Comma-separated list (e.g., "decision_required,tool_result,run_state_changed")
    - project_id: Filter by project
    - start_time: ISO format timestamp to start from
    - last_event_id: Resume from last event ID
    """
    try:
        # Parse event types
        event_type_list = None
        if event_types:
            event_type_list = [et.strip() for et in event_types.split(",")]

        # Parse start_time
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

        # Create SSE stream
        return StreamingResponse(
            event_stream_generator(
                workspace_id=workspace_id,
                store=store,
                event_types=event_type_list,
                project_id=project_id,
                start_time=start_time_dt,
                last_event_id=last_event_id,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
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
