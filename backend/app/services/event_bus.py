"""
In-memory event bus for real-time SSE delivery.

Events are published here after DB persistence.
SSE generators subscribe and receive events instantly via asyncio.Queue.
DB remains the source of truth; this is purely for real-time push.

Thread-safety: publish() is called from executor threads (via
asyncio.to_thread / run_in_executor in create_event callers).
We use loop.call_soon_threadsafe to safely enqueue from any thread.
"""

import asyncio
import logging
from collections import defaultdict
from typing import Dict, Set, Optional

logger = logging.getLogger(__name__)


class EventBus:
    """Per-workspace pub/sub using asyncio.Queue for each subscriber."""

    def __init__(self):
        # workspace_id -> set of subscriber queues
        self._subscribers: Dict[str, Set[asyncio.Queue]] = defaultdict(set)
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def subscribe(self, workspace_id: str) -> asyncio.Queue:
        """Create a new subscriber queue for a workspace. Returns the queue."""
        # Cache the event loop on first subscribe (always called from async context)
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                pass

        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subscribers[workspace_id].add(queue)
        logger.info(
            f"[EventBus] New subscriber for workspace={workspace_id}, "
            f"total={len(self._subscribers[workspace_id])}"
        )
        return queue

    def unsubscribe(self, workspace_id: str, queue: asyncio.Queue):
        """Remove a subscriber queue."""
        self._subscribers[workspace_id].discard(queue)
        if not self._subscribers[workspace_id]:
            del self._subscribers[workspace_id]
        logger.info(f"[EventBus] Unsubscribed from workspace={workspace_id}")

    def publish(self, workspace_id: str, event_data: dict):
        """
        Push event dict to all subscribers of a workspace.
        Thread-safe: can be called from any thread (executor or main loop).
        """
        subscribers = self._subscribers.get(workspace_id)
        if not subscribers:
            return

        loop = self._loop
        if loop is None or loop.is_closed():
            return

        for queue in list(subscribers):
            try:
                loop.call_soon_threadsafe(self._safe_put, queue, event_data)
            except RuntimeError:
                # Loop is closed
                pass

    @staticmethod
    def _safe_put(queue: asyncio.Queue, event_data: dict):
        """Put event data into queue, dropping if full."""
        try:
            queue.put_nowait(event_data)
        except asyncio.QueueFull:
            logger.warning("[EventBus] Queue full, dropping event")

    @property
    def subscriber_count(self) -> int:
        return sum(len(s) for s in self._subscribers.values())


# Global singleton
event_bus = EventBus()
