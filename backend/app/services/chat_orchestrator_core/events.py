"""Persist chat orchestrator events through the existing store path."""

import asyncio
import uuid
from datetime import datetime, timezone

from backend.app.models.mindscape import EventActor, EventType, MindEvent


def utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


async def persist_event(store, event: MindEvent) -> None:
    """Persist an event through the current executor-backed store write path."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    await loop.run_in_executor(None, lambda: store.create_event(event))


async def create_pipeline_event(
    *,
    store,
    workspace_id,
    profile_id,
    thread_id,
    project_id,
    stage,
    message,
    run_id,
):
    """Create a persisted pipeline stage event."""
    event = MindEvent(
        id=str(uuid.uuid4()),
        timestamp=utc_now(),
        actor=EventActor.SYSTEM,
        channel="local_workspace",
        profile_id=profile_id,
        project_id=project_id,
        workspace_id=workspace_id,
        thread_id=thread_id,
        event_type=EventType.PIPELINE_STAGE,
        payload={
            "stage": stage,
            "message": message,
            "run_id": run_id,
            "status": "running",
        },
        entity_ids=[],
        metadata={},
    )
    await persist_event(store, event)


async def create_error_event(
    *,
    store,
    workspace_id,
    profile_id,
    thread_id,
    error_msg,
    retry_data=None,
):
    """Create a persisted error event."""
    metadata = {"is_error": True}
    if retry_data:
        metadata["retry_data"] = retry_data
    event = MindEvent(
        id=str(uuid.uuid4()),
        timestamp=utc_now(),
        actor=EventActor.SYSTEM,
        channel="local_workspace",
        profile_id=profile_id,
        workspace_id=workspace_id,
        thread_id=thread_id,
        event_type=EventType.MESSAGE,
        payload={
            "message": f"Error processing request: {error_msg}",
            "type": "error",
        },
        entity_ids=[],
        metadata=metadata,
    )
    await persist_event(store, event)
