"""Compatibility shim for legacy compile-job task tracking."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True)
class CompileJobTaskRecord:
    job_id: str
    task: asyncio.Task | None = None


class CompileJobTaskRegistry:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self._lock = Lock()

    def snapshot(self) -> list[CompileJobTaskRecord]:
        with self._lock:
            return [
                CompileJobTaskRecord(job_id=job_id, task=task)
                for job_id, task in self._tasks.items()
            ]

    def register(self, job_id: str, task: asyncio.Task) -> None:
        with self._lock:
            self._tasks[job_id] = task

    def cancel(self, job_id: str) -> None:
        with self._lock:
            task = self._tasks.get(job_id)
        if task is not None and not task.done():
            task.cancel()

    def unregister(self, job_id: str) -> None:
        with self._lock:
            self._tasks.pop(job_id, None)


compile_job_task_registry = CompileJobTaskRegistry()
