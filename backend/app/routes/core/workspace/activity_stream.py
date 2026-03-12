"""
Workspace Activity Stream — SSE endpoint.

Provides a single Server-Sent Events stream for ALL workspace activity
(meeting stages, agent turns, task dispatch, task completion).

Backed by Redis Pub/Sub channel ``workspace:{id}:stream``.
"""

import asyncio
import json
import logging
import time

from fastapi import APIRouter, HTTPException, Path as PathParam, Request
from starlette.responses import StreamingResponse

logger = logging.getLogger(__name__)

router = APIRouter()

HEARTBEAT_INTERVAL_S = 15.0


@router.get("/{workspace_id}/activity-stream")
async def workspace_activity_stream(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    request: Request = None,
):
    """SSE stream for all workspace activity events.

    Events include:
    - ``meeting_stage``: deliberation stage transitions
    - ``mind_event``: agent turns, decisions, action items
    - ``task_dispatched`` / ``task_dispatch_failed``: dispatch lifecycle
    - ``dispatch_started`` / ``dispatch_completed``: batch dispatch summary
    - ``task_completed``: terminal task status change

    Falls back to 503 if Redis is unavailable.
    """
    from backend.app.services.cache.async_redis import (
        get_async_redis_client,
        subscribe_workspace_stream,
    )

    # Pre-check Redis availability
    client = await get_async_redis_client()
    if not client:
        raise HTTPException(
            status_code=503,
            detail="Activity stream unavailable: Redis not connected",
        )

    async def event_generator():
        last_heartbeat = time.monotonic()
        try:
            gen = subscribe_workspace_stream(workspace_id)
            # We need to handle both the subscription and heartbeat
            # Since subscribe_workspace_stream is an async generator that blocks,
            # we use asyncio.wait_for with a timeout for heartbeat
            async for event_data in gen:
                if request and await request.is_disconnected():
                    break

                payload = json.dumps(event_data, ensure_ascii=False)
                yield f"data: {payload}\n\n"
                last_heartbeat = time.monotonic()

        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.warning(
                "Activity stream error for workspace %s: %s",
                workspace_id,
                exc,
            )
            yield f"data: {json.dumps({'type': 'stream_error', 'error': str(exc)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
