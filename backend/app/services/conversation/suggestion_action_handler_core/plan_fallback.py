"""ExecutionPlan fallback helper for suggestion actions."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.app.core.domain_context import LocalDomainContext
from backend.app.models.workspace import ExecutionPlan, TaskPlan


async def execute_via_plan(
    handler: Any,
    *,
    pack_id: str,
    ctx: LocalDomainContext,
    message_id: str,
    files: List[str],
    message: str,
    project_id: Optional[str],
    task: Optional[Any],
    action_params: Dict[str, Any],
) -> Dict[str, Any]:
    """Execute pack via ExecutionPlan fallback."""
    plan = ExecutionPlan(
        message_id=message_id,
        workspace_id=ctx.workspace_id,
        tasks=[
            TaskPlan(
                pack_id=pack_id,
                task_type=pack_id,
                params={
                    **(task.params if task and task.params else {}),
                    **(action_params if action_params else {}),
                    "files": files,
                    "message": message,
                },
                side_effect_level=None,
                auto_execute=False,
                requires_cta=False,
            )
        ],
    )
    execution_results = await handler.execution_coordinator.execute_plan(
        execution_plan=plan,
        workspace_id=ctx.workspace_id,
        profile_id=ctx.actor_id,
        message_id=message_id,
        files=files,
        message=message,
        project_id=project_id,
    )
    return {"pack_id": pack_id, "execution_results": execution_results}
