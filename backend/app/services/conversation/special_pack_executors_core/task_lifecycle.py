"""Task lifecycle helpers for special pack executors."""

import logging
import uuid
from typing import Any, Dict, List

from backend.app.models.workspace import Task, TaskStatus
from backend.app.services.conversation.special_pack_executors_core.clock import (
    utc_now,
)

logger = logging.getLogger(__name__)


def create_running_task(
    *,
    tasks_store,
    workspace_id: str,
    message_id: str,
    files: List[str],
    message: str,
    pack_id: str = "semantic_seeds",
) -> Task:
    task = Task(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        message_id=message_id,
        execution_id=None,
        pack_id=pack_id,
        task_type="extract_intents",
        status=TaskStatus.RUNNING,
        params={"files": files, "message": message},
        result=None,
        created_at=utc_now(),
        started_at=utc_now(),
        completed_at=None,
        error=None,
    )
    tasks_store.create_task(task)
    logger.info(
        "SpecialPackExecutors: Created RUNNING task %s for semantic_seeds "
        "(pack_id=%s, workspace=%s)",
        task.id,
        pack_id,
        workspace_id,
    )
    return task


def complete_task(*, tasks_store, task: Task, execution_result: Dict[str, Any]) -> None:
    tasks_store.update_task_status(
        task_id=task.id,
        status=TaskStatus.SUCCEEDED,
        result=execution_result,
        completed_at=utc_now(),
    )
    logger.info("SpecialPackExecutors: Updated task %s to SUCCEEDED", task.id)


def emit_task_created(*, emitter, task: Task, pack_id: str) -> None:
    if not emitter:
        return
    emitter.emit_task_created(
        task_id=task.id,
        pack_id=pack_id,
        status=task.status.value,
        task_type=task.task_type,
        workspace_id=task.workspace_id,
    )


def emit_task_updated(*, emitter, task: Task, pack_id: str) -> None:
    if not emitter:
        return
    emitter.emit_task_updated(
        task_id=task.id,
        pack_id=pack_id,
        status=TaskStatus.SUCCEEDED.value,
        task_type=task.task_type,
        workspace_id=task.workspace_id,
    )
