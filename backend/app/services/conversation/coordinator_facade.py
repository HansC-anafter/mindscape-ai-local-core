"""Coordinator facade for plan and playbook execution."""

from typing import Any, Callable, Dict, List, Optional

from backend.app.core.domain_context import LocalDomainContext
from backend.app.models.workspace import ExecutionPlan
from backend.app.services.conversation.coordinator_facade_core import (
    create_execution_with_ctx as create_execution_with_ctx_helper,
    execute_plan as execute_plan_helper,
    execute_plan_with_ctx as execute_plan_with_ctx_helper,
    execute_playbook as execute_playbook_helper,
    execute_readonly_playbook,
    execute_readonly_task,
    resolve_mind_lens,
)
from backend.app.services.conversation.error_policy import ErrorPolicy
from backend.app.services.conversation.execution_context_builder import (
    ExecutionContextBuilder,
)
from backend.app.services.conversation.execution_launcher import ExecutionLauncher
from backend.app.services.conversation.plan_executor import PlanExecutor
from backend.app.services.conversation.plan_preparer import PlanPreparer
from backend.app.services.conversation.playbook_resolver import PlaybookResolver
from backend.app.services.conversation.special_pack_executors import SpecialPackExecutors
from backend.app.services.conversation.suggestion_card_creator import (
    SuggestionCardCreator,
)
from backend.app.services.conversation.task_creator import TaskCreator
from backend.app.services.conversation.task_events_emitter import TaskEventsEmitter
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.stores.timeline_items_store import TimelineItemsStore


class CoordinatorFacade:
    """Facade for execution coordination backed by split helper modules."""

    def __init__(
        self,
        store: MindscapeStore,
        tasks_store: TasksStore,
        timeline_items_store: TimelineItemsStore,
        task_manager,
        plan_builder,
        playbook_runner,
        message_generator,
        default_locale: str = "en",
        playbook_service=None,
    ):
        self.store = store
        self.tasks_store = tasks_store
        self.timeline_items_store = timeline_items_store
        self.task_manager = task_manager
        self.plan_builder = plan_builder
        self.playbook_runner = playbook_runner
        self.message_generator = message_generator
        self.default_locale = default_locale
        self.playbook_service = playbook_service

        from backend.app.services.config_store import ConfigStore
        from backend.app.services.playbook_run_executor import PlaybookRunExecutor

        self.config_store = ConfigStore()
        self.playbook_run_executor = PlaybookRunExecutor()
        self.plan_preparer = PlanPreparer(store=store)
        self.playbook_resolver = PlaybookResolver(
            default_locale=default_locale,
            playbook_service=playbook_service,
        )
        self.execution_launcher = ExecutionLauncher(
            playbook_service=playbook_service,
            playbook_run_executor=self.playbook_run_executor,
            default_locale=default_locale,
        )
        self.error_policy = ErrorPolicy()
        self.execution_context_builder = ExecutionContextBuilder(
            store=store,
            tasks_store=tasks_store,
            playbook_resolver=self.playbook_resolver,
        )
        self.task_creator = TaskCreator(
            tasks_store=tasks_store,
            execution_context_builder=self.execution_context_builder,
        )
        self.plan_executor = PlanExecutor(
            plan_preparer=self.plan_preparer,
            playbook_resolver=self.playbook_resolver,
            execution_launcher=self.execution_launcher,
            error_policy=self.error_policy,
            plan_builder=plan_builder,
            tasks_store=tasks_store,
        )
        self.suggestion_card_creator = SuggestionCardCreator(
            tasks_store=tasks_store,
            playbook_service=playbook_service,
            message_generator=message_generator,
            default_locale=default_locale,
        )
        self.special_pack_executors = SpecialPackExecutors(
            tasks_store=tasks_store,
            timeline_items_store=timeline_items_store,
            store=store,
            config_store=self.config_store,
        )

    async def execute_plan(
        self,
        execution_plan: ExecutionPlan,
        workspace_id: str,
        profile_id: str,
        message_id: str,
        files: List[str],
        message: str,
        project_id: Optional[str] = None,
        task_event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """Execute an execution plan based on side effect level."""
        return await execute_plan_helper(
            facade=self,
            execution_plan=execution_plan,
            workspace_id=workspace_id,
            profile_id=profile_id,
            message_id=message_id,
            files=files,
            message=message,
            project_id=project_id,
            task_event_callback=task_event_callback,
        )

    async def execute_plan_with_ctx(
        self,
        execution_plan: ExecutionPlan,
        ctx: LocalDomainContext,
        message_id: str,
        files: List[str],
        message: str,
        project_id: Optional[str] = None,
        task_event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        prevent_suggestion_creation: bool = False,
    ) -> Dict[str, Any]:
        """Execute an execution plan with an existing local domain context."""
        return await execute_plan_with_ctx_helper(
            facade=self,
            execution_plan=execution_plan,
            ctx=ctx,
            message_id=message_id,
            files=files,
            message=message,
            project_id=project_id,
            task_event_callback=task_event_callback,
            prevent_suggestion_creation=prevent_suggestion_creation,
        )

    async def _resolve_mind_lens(
        self,
        execution_plan: ExecutionPlan,
        ctx: LocalDomainContext,
    ) -> None:
        """Resolve Mind Lens data when configured."""
        await resolve_mind_lens(execution_plan=execution_plan, ctx=ctx)

    async def _execute_readonly_task(
        self,
        task_plan,
        ctx: LocalDomainContext,
        message_id: str,
        files: List[str],
        message: str,
        project_id: Optional[str],
        event_emitter: TaskEventsEmitter,
    ) -> Optional[Dict[str, Any]]:
        """Execute a readonly task automatically."""
        return await execute_readonly_task(
            facade=self,
            task_plan=task_plan,
            ctx=ctx,
            message_id=message_id,
            files=files,
            message=message,
            project_id=project_id,
            event_emitter=event_emitter,
        )

    async def execute_playbook(
        self,
        playbook_code: str,
        playbook_context: Dict[str, Any],
        workspace_id: str,
        profile_id: str,
        message_id: str,
        project_id: Optional[str],
    ) -> Dict[str, Any]:
        """Execute a playbook based on side effect level."""
        return await execute_playbook_helper(
            facade=self,
            playbook_code=playbook_code,
            playbook_context=playbook_context,
            workspace_id=workspace_id,
            profile_id=profile_id,
            message_id=message_id,
            project_id=project_id,
        )

    async def create_execution_with_ctx(
        self,
        playbook_code: str,
        playbook_context: Dict[str, Any],
        ctx: LocalDomainContext,
        message_id: str,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create execution based on side effect level and suggestion flags."""
        return await create_execution_with_ctx_helper(
            facade=self,
            playbook_code=playbook_code,
            playbook_context=playbook_context,
            ctx=ctx,
            message_id=message_id,
            project_id=project_id,
        )

    async def _execute_readonly_playbook(
        self,
        playbook_code: str,
        playbook_context: Dict[str, Any],
        ctx: LocalDomainContext,
        message_id: str,
        project_id: Optional[str],
        event_emitter: TaskEventsEmitter,
    ) -> Dict[str, Any]:
        """Execute a readonly playbook automatically."""
        return await execute_readonly_playbook(
            facade=self,
            playbook_code=playbook_code,
            playbook_context=playbook_context,
            ctx=ctx,
            message_id=message_id,
            project_id=project_id,
            event_emitter=event_emitter,
        )
