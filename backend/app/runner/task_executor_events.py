"""Task executor event emission helpers."""

import logging
from typing import Any, Dict

from backend.app.models.workspace import Task
from backend.app.services.mindscape_store import MindscapeStore

logger = logging.getLogger(__name__)


def _emit_run_state_changed_for_task(
    task: Task,
    *,
    previous_state: str,
    new_state: str,
    reason: str,
) -> None:
    """Emit a workspace lifecycle event for runner-managed task transitions."""
    try:
        from backend.app.services.playbook_runner_core.run_state import (
            build_run_state_changed_event,
        )

        ctx = task.execution_context if isinstance(task.execution_context, dict) else {}
        inputs = None
        if isinstance(task.params, dict) and task.params:
            inputs = task.params
        elif isinstance(ctx.get("inputs"), dict):
            inputs = ctx.get("inputs")
        elif isinstance(task.params, dict):
            inputs = task.params
        event_inputs: Dict[str, Any] = inputs if isinstance(inputs, dict) else {}
        playbook_code = (
            event_inputs.get("playbook_code")
            or (ctx.get("playbook_code") if isinstance(ctx, dict) else None)
            or task.pack_id
            or ""
        )

        event = build_run_state_changed_event(
            profile_id=(
                getattr(task, "profile_id", None)
                or (ctx.get("profile_id") if isinstance(ctx, dict) else None)
                or "default-user"
            ),
            project_id=task.project_id,
            workspace_id=task.workspace_id,
            execution_id=task.execution_id or str(task.id),
            previous_state=previous_state,
            new_state=new_state,
            reason=reason,
            playbook_code=playbook_code,
            inputs=inputs,
        )
        MindscapeStore().create_event(event)
    except Exception as emit_error:
        logger.warning(
            "Failed to emit %s RUN_STATE_CHANGED event for task %s (%s): %s",
            new_state,
            task.id,
            task.execution_id,
            emit_error,
        )
