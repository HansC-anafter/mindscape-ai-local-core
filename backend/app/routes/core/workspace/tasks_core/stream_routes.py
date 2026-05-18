import asyncio
import json

from fastapi import APIRouter, Request
from fastapi import Path as PathParam
from starlette.responses import StreamingResponse

from .streaming import _subscribe_execution_stream, _unsubscribe_execution_stream

router = APIRouter()


@router.get("/{workspace_id}/executions/{execution_id}/stream")
async def stream_execution_events(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    execution_id: str = PathParam(..., description="Execution ID"),
    request: Request = None,
):
    """SSE stream for execution progress events."""
    state, queue = await _subscribe_execution_stream(workspace_id, execution_id)

    async def event_generator():
        try:
            while True:
                if request and await request.is_disconnected():
                    return
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=5)
                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    return

                yield f"data: {payload}\n\n"

                try:
                    parsed = json.loads(payload)
                except Exception:
                    parsed = {}
                if parsed.get("type") == "stream_end":
                    return
        finally:
            await _unsubscribe_execution_stream(execution_id, state, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
