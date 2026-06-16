"""In-process host runtime event fanout.

Persisted lifecycle events live in Postgres. This stream is only for live
delivery to connected RUNS surfaces and bridge clients; reconnects must replay
from the store with last_seq.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import AsyncIterator

from .models import HostRuntimeEvent


class HostRuntimeEventStream:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[HostRuntimeEvent]]] = defaultdict(set)
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def subscribe(self, session_id: str) -> AsyncIterator[asyncio.Queue[HostRuntimeEvent]]:
        queue: asyncio.Queue[HostRuntimeEvent] = asyncio.Queue(maxsize=200)
        async with self._lock:
            self._subscribers[session_id].add(queue)
        try:
            yield queue
        finally:
            async with self._lock:
                subscribers = self._subscribers.get(session_id)
                if subscribers and queue in subscribers:
                    subscribers.remove(queue)
                if subscribers is not None and not subscribers:
                    self._subscribers.pop(session_id, None)

    async def publish(self, event: HostRuntimeEvent) -> None:
        async with self._lock:
            subscribers = list(self._subscribers.get(event.session_id, set()))
        for queue in subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                _ = queue.get_nowait()
                queue.put_nowait(event)


_event_stream = HostRuntimeEventStream()


def get_host_runtime_event_stream() -> HostRuntimeEventStream:
    return _event_stream
