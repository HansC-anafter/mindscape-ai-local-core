"""Coalesce identical deep-readiness requests on the active API event loop."""

from __future__ import annotations

import asyncio
import copy
import time
import weakref
from collections.abc import Awaitable, Callable, Hashable
from threading import Lock
from typing import Any


class ReadinessRequestCoordinator:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._cache: dict[Hashable, tuple[float, Any]] = {}
        self._inflight: dict[Hashable, asyncio.Task[Any]] = {}

    async def run(
        self,
        *,
        key: Hashable,
        producer: Callable[[], Awaitable[Any]],
        ttl_seconds: float = 0.0,
        force: bool = False,
    ) -> Any:
        async with self._lock:
            if not force and ttl_seconds > 0:
                cached = self._cache.get(key)
                if cached and time.monotonic() - cached[0] < ttl_seconds:
                    return copy.deepcopy(cached[1])

            task = self._inflight.get(key)
            if task is None:
                task = asyncio.create_task(
                    self._produce(
                        key=key,
                        producer=producer,
                        ttl_seconds=ttl_seconds,
                    )
                )
                self._inflight[key] = task

        result = await asyncio.shield(task)
        return copy.deepcopy(result)

    async def _produce(
        self,
        *,
        key: Hashable,
        producer: Callable[[], Awaitable[Any]],
        ttl_seconds: float,
    ) -> Any:
        current_task = asyncio.current_task()
        try:
            result = await producer()
            if ttl_seconds > 0:
                async with self._lock:
                    self._cache[key] = (time.monotonic(), copy.deepcopy(result))
            return result
        finally:
            async with self._lock:
                if self._inflight.get(key) is current_task:
                    self._inflight.pop(key, None)


_COORDINATORS: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop, ReadinessRequestCoordinator
] = weakref.WeakKeyDictionary()
_COORDINATORS_LOCK = Lock()


def get_readiness_request_coordinator() -> ReadinessRequestCoordinator:
    loop = asyncio.get_running_loop()
    with _COORDINATORS_LOCK:
        coordinator = _COORDINATORS.get(loop)
        if coordinator is None:
            coordinator = ReadinessRequestCoordinator()
            _COORDINATORS[loop] = coordinator
        return coordinator


def reset_readiness_request_coordinators() -> None:
    with _COORDINATORS_LOCK:
        _COORDINATORS.clear()


__all__ = [
    "ReadinessRequestCoordinator",
    "get_readiness_request_coordinator",
    "reset_readiness_request_coordinators",
]
