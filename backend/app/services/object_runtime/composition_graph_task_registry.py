"""In-process task registry for executable composition graph runs."""

from __future__ import annotations

import asyncio
from typing import Dict, Optional

_TASKS: Dict[str, asyncio.Task[None]] = {}


def register_graph_run_task(graph_run_id: str, task: asyncio.Task[None]) -> None:
    _TASKS[graph_run_id] = task


def get_graph_run_task(graph_run_id: str) -> Optional[asyncio.Task[None]]:
    task = _TASKS.get(graph_run_id)
    if task is not None and task.done():
        _TASKS.pop(graph_run_id, None)
        return None
    return task


def discard_graph_run_task(graph_run_id: str) -> None:
    _TASKS.pop(graph_run_id, None)
