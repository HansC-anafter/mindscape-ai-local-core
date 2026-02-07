import asyncio
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class RegisteredExecutionTask:
    execution_id: str
    task: asyncio.Task


class ExecutionTaskRegistry:
    def __init__(self) -> None:
        self._tasks: Dict[str, RegisteredExecutionTask] = {}

    def register(self, execution_id: str, task: asyncio.Task) -> None:
        if not execution_id:
            return
        self._tasks[execution_id] = RegisteredExecutionTask(execution_id=execution_id, task=task)

    def unregister(self, execution_id: str) -> None:
        if not execution_id:
            return
        self._tasks.pop(execution_id, None)

    def get(self, execution_id: str) -> Optional[RegisteredExecutionTask]:
        if not execution_id:
            return None
        return self._tasks.get(execution_id)

    def has(self, execution_id: str) -> bool:
        return self.get(execution_id) is not None

    def cancel(self, execution_id: str) -> bool:
        item = self.get(execution_id)
        if not item:
            return False
        try:
            item.task.cancel()
        except Exception:
            return False
        return True


execution_task_registry = ExecutionTaskRegistry()

