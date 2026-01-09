"""
Cloud Connector - Heartbeat Monitor

Monitors connection health and sends periodic heartbeat messages.
"""

import asyncio
import json
import logging
from typing import Optional

from websockets.client import WebSocketClientProtocol

logger = logging.getLogger(__name__)


class HeartbeatMonitor:
    """
    Heartbeat monitor for WebSocket connection.

    Sends periodic ping messages and monitors connection health.
    """

    def __init__(
        self,
        websocket: WebSocketClientProtocol,
        interval: float = 30.0,
    ):
        """
        Initialize heartbeat monitor.

        Args:
            websocket: WebSocket connection
            interval: Heartbeat interval in seconds (default: 30)
        """
        self.websocket = websocket
        self.interval = interval
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        """Start heartbeat monitoring."""
        if self._task and not self._task.done():
            logger.warning("Heartbeat monitor already running")
            return

        self._stop_event.clear()
        self._task = asyncio.create_task(self._heartbeat_loop())
        logger.info(f"Heartbeat monitor started (interval: {self.interval}s)")

    async def stop(self) -> None:
        """Stop heartbeat monitoring."""
        self._stop_event.set()
        if self._task:
            await self._task
            self._task = None
        logger.info("Heartbeat monitor stopped")

    async def _heartbeat_loop(self) -> None:
        """
        Main heartbeat loop.

        Note: Heartbeat is now handled by Cloud sending ping messages.
        This monitor is kept for backward compatibility but does not send pings.
        Local-Core responds to Cloud's ping with pong in connector._handle_message.
        """
        try:
            while not self._stop_event.is_set():
                await asyncio.sleep(self.interval)

                if self._stop_event.is_set():
                    break

                logger.debug("Heartbeat monitor active (Cloud sends ping, Local responds with pong)")

        except asyncio.CancelledError:
            logger.info("Heartbeat loop cancelled")
        except Exception as e:
            logger.error(f"Heartbeat loop error: {e}", exc_info=True)
