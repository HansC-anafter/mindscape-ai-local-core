"""
Activity Relay — Cloud Connector component.

Subscribes to ALL workspace activity events via Redis PSUBSCRIBE and
forwards them as ``activity_event`` WebSocket messages to Site-Hub.

This gives Site-Hub (and downstream channels like LINE/IG task pages)
real-time visibility into meeting stages, dispatch, and task completion.

Start/stop lifecycle is managed by CloudConnector.connect/disconnect.
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional

from websockets.client import WebSocketClientProtocol

logger = logging.getLogger(__name__)


class ActivityRelay:
    """Relay workspace activity events from Redis to Cloud WS.

    Uses Redis ``PSUBSCRIBE workspace:*:stream`` to capture events from
    all workspaces. Each event is forwarded as a JSON WS message with
    ``type: "activity_event"``.

    Non-fatal: if Redis is unavailable or WS send fails, the relay
    logs and continues (or retries after backoff).
    """

    def __init__(self, websocket: WebSocketClientProtocol, device_id: str):
        self._ws = websocket
        self._device_id = device_id
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        """Start the relay background task."""
        if self._task and not self._task.done():
            return
        self._running = True
        self._task = asyncio.create_task(self._relay_loop())
        logger.info("[ActivityRelay] Started")

    async def stop(self) -> None:
        """Stop the relay background task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("[ActivityRelay] Stopped")

    async def _relay_loop(self) -> None:
        """Subscribe to Redis and forward events over WS."""
        while self._running:
            try:
                from backend.app.services.cache.async_redis import (
                    psubscribe_all_workspace_streams,
                )

                async for (
                    workspace_id,
                    event_data,
                ) in psubscribe_all_workspace_streams():
                    if not self._running:
                        break
                    await self._forward(workspace_id, event_data)

            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.warning(
                    "[ActivityRelay] Subscription error, retrying in 5s: %s", exc
                )
                if self._running:
                    await asyncio.sleep(5)

    async def _forward(self, workspace_id: str, event_data: Dict[str, Any]) -> None:
        """Forward a single event to Cloud WS."""
        try:
            msg = json.dumps(
                {
                    "type": "activity_event",
                    "workspace_id": workspace_id,
                    "payload": event_data,
                },
                ensure_ascii=False,
            )
            await self._ws.send(msg)
        except Exception as exc:
            # WS send failure — log but don't crash the relay
            logger.debug("[ActivityRelay] WS send failed: %s", exc)
