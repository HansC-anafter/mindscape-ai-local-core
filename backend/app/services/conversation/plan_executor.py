"""Plan executor facade."""

from typing import Any, Dict, List, Optional

from backend.app.core.domain_context import LocalDomainContext
from backend.app.models.workspace import ExecutionPlan, SideEffectLevel
from backend.app.services.conversation.error_policy import ErrorPolicy
from backend.app.services.conversation.execution_launcher import ExecutionLauncher
from backend.app.services.conversation.plan_executor_core.auto_execute import (
    determine_auto_execute as determine_auto_execute_helper,
)
from backend.app.services.conversation.plan_executor_core.failure import (
    handle_execution_failure as handle_execution_failure_helper,
)
from backend.app.services.conversation.plan_executor_core.orchestration import (
    ExecutionOrchestrationState,
)
from backend.app.services.conversation.plan_executor_core.readonly import (
    execute_readonly_task as execute_readonly_task_helper,
)
from backend.app.services.conversation.plan_executor_core.runtime import (
    execute_plan as execute_plan_helper,
)
from backend.app.services.conversation.plan_executor_core.soft_write import (
    handle_soft_write_task as handle_soft_write_task_helper,
)
from backend.app.services.conversation.plan_preparer import PlanPreparer
from backend.app.services.conversation.playbook_resolver import PlaybookResolver
from backend.app.services.conversation.task_events_emitter import TaskEventsEmitter


class PlanExecutor:
    """Execute execution plans through modular core helpers."""

    def __init__(
        self,
        plan_preparer: PlanPreparer,
        playbook_resolver: PlaybookResolver,
        execution_launcher: ExecutionLauncher,
        error_policy: ErrorPolicy,
        plan_builder,
        tasks_store,
    ):
        self.plan_preparer = plan_preparer
        self.playbook_resolver = playbook_resolver
        self.execution_launcher = execution_launcher
        self.error_policy = error_policy
        self.plan_builder = plan_builder
        self.tasks_store = tasks_store

    async def execute_plan(
        self,
        execution_plan: ExecutionPlan,
        ctx: LocalDomainContext,
        message_id: str,
        files: List[str],
        message: str,
        project_id: Optional[str],
        event_emitter: TaskEventsEmitter,
        workspace,
        prevent_suggestion_creation: bool = False,
        suggestion_creator=None,
    ) -> Dict[str, Any]:
        return await execute_plan_helper(
            self,
            execution_plan=execution_plan,
            ctx=ctx,
            message_id=message_id,
            files=files,
            message=message,
            project_id=project_id,
            event_emitter=event_emitter,
            workspace=workspace,
            prevent_suggestion_creation=prevent_suggestion_creation,
            suggestion_creator=suggestion_creator,
        )

    def _determine_auto_execute(
        self,
        task_plan,
        side_effect_level: SideEffectLevel,
        execution_mode: str,
        execution_priority: str,
        auto_exec_config: Optional[Dict[str, Any]],
    ) -> bool:
        return determine_auto_execute_helper(
            task_plan=task_plan,
            side_effect_level=side_effect_level,
            execution_mode=execution_mode,
            execution_priority=execution_priority,
            auto_exec_config=auto_exec_config,
        )

    async def _execute_readonly_task(
        self,
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
        return await execute_readonly_task_helper(
            self,
            task_plan=task_plan,
            ctx=ctx,
            message_id=message_id,
            files=files,
            message=message,
            project_id=project_id,
            event_emitter=event_emitter,
            execution_plan=execution_plan,
            orchestration_state=orchestration_state,
        )

    async def _handle_execution_failure(
        self,
        task_plan,
        ctx: LocalDomainContext,
        message_id: str,
        results: Dict[str, Any],
        prevent_suggestion_creation: bool,
        suggestion_creator,
        event_emitter: TaskEventsEmitter,
    ) -> None:
        await handle_execution_failure_helper(
            self,
            task_plan=task_plan,
            ctx=ctx,
            message_id=message_id,
            results=results,
            prevent_suggestion_creation=prevent_suggestion_creation,
            suggestion_creator=suggestion_creator,
            event_emitter=event_emitter,
        )

    async def _handle_soft_write_task(
        self,
        task_plan,
        ctx: LocalDomainContext,
        message_id: str,
        files: List[str],
        message: str,
        project_id: Optional[str],
        event_emitter: TaskEventsEmitter,
        auto_exec_config: Optional[Dict[str, Any]],
        execution_priority: str,
        prevent_suggestion_creation: bool,
        suggestion_creator,
    ) -> Optional[Dict[str, Any]]:
        return await handle_soft_write_task_helper(
            self,
            task_plan=task_plan,
            ctx=ctx,
            message_id=message_id,
            files=files,
            message=message,
            project_id=project_id,
            event_emitter=event_emitter,
            auto_exec_config=auto_exec_config,
            execution_priority=execution_priority,
            prevent_suggestion_creation=prevent_suggestion_creation,
            suggestion_creator=suggestion_creator,
        )
