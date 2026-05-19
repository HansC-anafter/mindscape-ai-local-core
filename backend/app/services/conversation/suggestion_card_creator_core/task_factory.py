"""Task construction helpers for suggestion card creation."""

import uuid
from typing import Any, Dict

from backend.app.models.workspace import Task, TaskStatus
from backend.app.services.conversation.suggestion_card_creator_core.clock import (
    utc_now,
)


def build_suggestion_task(
    *,
    task_plan,
    workspace_id: str,
    message_id: str,
    llm_analysis: Dict[str, Any],
) -> Task:
    return Task(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        message_id=message_id,
        execution_id=None,
        pack_id=task_plan.pack_id,
        task_type="suggestion",
        status=TaskStatus.PENDING,
        params=task_plan.params,
        result={
            "suggestion": True,
            "pack_id": task_plan.pack_id,
            "requires_cta": True,
            "llm_analysis": llm_analysis,
        },
        created_at=utc_now(),
        started_at=None,
        completed_at=None,
        error=None,
    )


def build_playbook_suggestion_task(
    *,
    playbook_code: str,
    playbook_context: Dict[str, Any],
    workspace_id: str,
    message_id: str,
    llm_analysis: Dict[str, Any],
) -> Task:
    return Task(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        message_id=message_id,
        execution_id=None,
        pack_id=playbook_code,
        task_type="suggestion",
        status=TaskStatus.PENDING,
        params={
            "playbook_code": playbook_code,
            "context": playbook_context,
            "llm_analysis": llm_analysis,
        },
        result={
            "suggestion": True,
            "playbook_code": playbook_code,
            "requires_cta": True,
            "llm_analysis": llm_analysis,
        },
        created_at=utc_now(),
        started_at=None,
        completed_at=None,
        error=None,
    )


def emit_task_created(*, event_emitter, task: Task, pack_id: str) -> None:
    event_emitter.emit_task_created(
        task_id=task.id,
        pack_id=pack_id,
        status=task.status.value,
        task_type=task.task_type,
        workspace_id=task.workspace_id,
    )
