"""Pipeline stage event persistence."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from backend.app.models.mindscape import EventActor, EventType, MindEvent

logger = logging.getLogger(__name__)


async def emit_pipeline_stage(
    *,
    pipeline: Any,
    workspace_id,
    profile_id,
    thread_id,
    project_id,
    stage,
    message_text,
    run_id,
) -> None:
    """Persist a PIPELINE_STAGE event."""
    event = MindEvent(
        id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
        actor=EventActor.SYSTEM,
        channel="local_workspace",
        profile_id=profile_id,
        project_id=project_id,
        workspace_id=workspace_id,
        thread_id=thread_id,
        event_type=EventType.PIPELINE_STAGE,
        payload={
            "stage": stage,
            "message": message_text,
            "run_id": run_id,
            "status": "running",
        },
        entity_ids=[],
        metadata={},
    )
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        lambda: pipeline.store.create_event(event),
    )
    logger.info("[PipelineCore] Pipeline stage: %s", stage)
