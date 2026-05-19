"""Plan executor readonly task launch."""

import logging
from typing import Any, Dict, List, Optional

from backend.app.core.domain_context import LocalDomainContext
from backend.app.models.playbook import PlanContext
from backend.app.models.workspace import ExecutionPlan
from backend.app.services.conversation.plan_executor_core.orchestration import (
    ExecutionOrchestrationState,
    register_execution_with_orchestrator,
)
from backend.app.services.conversation.task_events_emitter import TaskEventsEmitter

logger = logging.getLogger(__name__)


async def execute_readonly_task(
    executor,
    task_plan,
    ctx: LocalDomainContext,
    message_id: str,
    files: List[str],
    message: str,
    project_id: Optional[str],
    event_emitter: TaskEventsEmitter,
    execution_plan: Optional[ExecutionPlan] = None,
    orchestration_state: Optional[ExecutionOrchestrationState] = None,
) -> Optional[Dict[str, Any]]:
    pack_id = task_plan.pack_id
    prepared_plan = await executor.plan_preparer.prepare_plan(
        task_plan=task_plan,
        ctx=ctx,
        message_id=message_id,
        files=files,
        message=message,
        project_id=project_id,
    )
    resolved_playbook = await executor.playbook_resolver.resolve(
        pack_id=prepared_plan.pack_id, ctx=ctx
    )
    if not resolved_playbook:
        executor.error_policy.warn_and_continue(
            f"Could not resolve playbook for pack {pack_id}"
        )
        return None

    try:
        if not execution_plan:
            return {
                "pack_id": pack_id,
                "playbook_code": resolved_playbook.code,
                "execution_id": None,
            }

        plan_context = PlanContext(
            plan_summary=execution_plan.plan_summary or "",
            reasoning=execution_plan.reasoning or "",
            steps=[
                step.model_dump() if hasattr(step, "model_dump") else step
                for step in execution_plan.steps
            ],
            dependencies=(
                task_plan.params.get("depends_on", []) if task_plan.params else []
            ),
        )
        task_id = task_plan.params.get("step_id") if task_plan.params else None
        try:
            launch_result = await executor.execution_launcher.launch(
                playbook_code=resolved_playbook.code,
                inputs=prepared_plan.playbook_inputs,
                ctx=ctx,
                project_meta=prepared_plan.project_meta,
                project_id=project_id,
                plan_id=execution_plan.id,
                task_id=task_id,
                plan_context=plan_context,
                trace_id=message_id,
            )
        except Exception as exc:
            logger.error(f"Failed to launch execution: {exc}", exc_info=True)
            raise

        execution_id = launch_result.get("execution_id")
        if not execution_id:
            executor.error_policy.handle_missing_execution_id(
                resolved_playbook.code, launch_result.get("raw_result")
            )

        register_execution_with_orchestrator(
            orchestration_state,
            execution_id,
            message_id,
        )
        if execution_id:
            _emit_task_created(
                executor,
                event_emitter,
                ctx,
                pack_id,
                resolved_playbook.code,
                execution_id,
            )

        return {
            "pack_id": pack_id,
            "playbook_code": resolved_playbook.code,
            "execution_id": execution_id,
        }
    except Exception as exc:
        executor.error_policy.handle_execution_error(
            f"launch playbook {resolved_playbook.code}", exc, raise_on_error=True
        )


def _emit_task_created(
    executor,
    event_emitter: TaskEventsEmitter,
    ctx: LocalDomainContext,
    pack_id: str,
    playbook_code: str,
    execution_id: str,
) -> None:
    task = executor.tasks_store.get_task_by_execution_id(execution_id)
    if task:
        event_emitter.emit_task_created(
            task_id=task.id,
            pack_id=pack_id,
            playbook_code=playbook_code,
            status=task.status.value if hasattr(task.status, "value") else str(task.status),
            task_type=task.task_type,
            workspace_id=ctx.workspace_id,
            execution_id=execution_id,
        )
    else:
        event_emitter.emit_task_created(
            task_id=execution_id,
            pack_id=pack_id,
            playbook_code=playbook_code,
            status="running",
            task_type="playbook_execution",
            workspace_id=ctx.workspace_id,
            execution_id=execution_id,
        )
