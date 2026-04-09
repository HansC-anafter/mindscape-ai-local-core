import asyncio
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class RegisteredCompileJobTask:
    job_id: str
    task: asyncio.Task


class CompileJobTaskRegistry:
    def __init__(self) -> None:
        self._tasks: Dict[str, RegisteredCompileJobTask] = {}

    def register(self, job_id: str, task: asyncio.Task) -> None:
        if not job_id:
            return
        self._tasks[job_id] = RegisteredCompileJobTask(job_id=job_id, task=task)

    def unregister(self, job_id: str) -> None:
        if not job_id:
            return
        self._tasks.pop(job_id, None)

    def get(self, job_id: str) -> Optional[RegisteredCompileJobTask]:
        if not job_id:
            return None
        return self._tasks.get(job_id)

    def has(self, job_id: str) -> bool:
        return self.get(job_id) is not None

    def snapshot(self) -> list[RegisteredCompileJobTask]:
        return list(self._tasks.values())

    def cancel(self, job_id: str) -> bool:
        item = self.get(job_id)
        if not item:
            return False
        try:
            item.task.cancel()
        except Exception:
            return False
        return True


compile_job_task_registry = CompileJobTaskRegistry()
