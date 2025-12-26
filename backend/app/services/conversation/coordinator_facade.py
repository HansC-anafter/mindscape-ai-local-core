"""
Coordinator Facade

Facade for execution coordination that integrates all coordination modules.
Provides unified interface for plan execution and playbook coordination.
"""

import logging
import sys
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
import uuid

from ...models.workspace import (
    Task,
    TaskStatus,
    TimelineItem,
    TimelineItemType,
    SideEffectLevel,
    ExecutionPlan,
)
from ...models.mindscape import MindEvent, EventType, EventActor
from ...services.mindscape_store import MindscapeStore
from ...services.stores.tasks_store import TasksStore
from ...services.stores.timeline_items_store import TimelineItemsStore
from ...core.domain_context import LocalDomainContext

from .plan_preparer import PlanPreparer, PreparedPlan
from .playbook_resolver import PlaybookResolver, ResolvedPlaybook
from .execution_launcher import ExecutionLauncher
from .task_events_emitter import TaskEventsEmitter
from .error_policy import ErrorPolicy, PlaybookNotFoundError
from .execution_context_builder import ExecutionContextBuilder
from .task_creator import TaskCreator
from .plan_executor import PlanExecutor
from .suggestion_card_creator import SuggestionCardCreator
from .special_pack_executors import SpecialPackExecutors

logger = logging.getLogger(__name__)


class CoordinatorFacade:
    """
    Facade for execution coordination

    Integrates PlanPreparer, PlaybookResolver, ExecutionLauncher,
    TaskEventsEmitter, and ErrorPolicy to provide unified coordination interface.
    Handles Mind Lens resolution, execution_mode/threshold logic.
    """

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
        """
        Initialize CoordinatorFacade

        Args:
            store: MindscapeStore instance
            tasks_store: TasksStore instance
            timeline_items_store: TimelineItemsStore instance
            task_manager: TaskManager instance
            plan_builder: PlanBuilder instance
            playbook_runner: PlaybookRunner instance
            message_generator: MessageGenerator instance
            default_locale: Default locale for i18n
            playbook_service: Optional PlaybookService instance
        """
        self.store = store
        self.tasks_store = tasks_store
        self.timeline_items_store = timeline_items_store
        self.task_manager = task_manager
        self.plan_builder = plan_builder
        self.playbook_runner = playbook_runner
        self.message_generator = message_generator
        self.default_locale = default_locale
        self.playbook_service = playbook_service

        from ...services.config_store import ConfigStore
        from ...services.playbook_run_executor import PlaybookRunExecutor

        self.config_store = ConfigStore(db_path=store.db_path)
        self.playbook_run_executor = PlaybookRunExecutor()

        # Initialize coordination modules
        self.plan_preparer = PlanPreparer(store=store)
        self.playbook_resolver = PlaybookResolver(
            default_locale=default_locale, playbook_service=playbook_service
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

        # Initialize further split modules
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
        """
        Execute execution plan based on side_effect_level

        Args:
            execution_plan: Execution plan with tasks
            workspace_id: Workspace ID
            profile_id: User profile ID
            message_id: Message/event ID
            files: List of file IDs
            message: User message
            project_id: Optional project ID
            task_event_callback: Optional task event callback

        Returns:
            Dict with execution results
        """
        ctx = LocalDomainContext(
            actor_id=profile_id, workspace_id=workspace_id, tags={"mode": "local"}
        )
        return await self.execute_plan_with_ctx(
            execution_plan=execution_plan,
            ctx=ctx,
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
        """
        Execute execution plan based on side_effect_level (using LocalDomainContext)

        Args:
            execution_plan: Execution plan with tasks
            ctx: Execution context
            message_id: Message/event ID
            files: List of file IDs
            message: User message
            project_id: Optional project ID
            task_event_callback: Optional task event callback
            prevent_suggestion_creation: Whether to prevent suggestion creation

        Returns:
            Dict with execution results
        """
        # Resolve Mind Lens if not already set
        await self._resolve_mind_lens(execution_plan, ctx)

        # Initialize event emitter
        event_emitter = TaskEventsEmitter(callback=task_event_callback)

        # Get workspace
        workspace = self.store.workspaces.get_workspace(ctx.workspace_id)

        # Use PlanExecutor to execute plan
        return await self.plan_executor.execute_plan(
            execution_plan=execution_plan,
            ctx=ctx,
            message_id=message_id,
            files=files,
            message=message,
            project_id=project_id,
            event_emitter=event_emitter,
            workspace=workspace,
            prevent_suggestion_creation=prevent_suggestion_creation,
            suggestion_creator=self.suggestion_card_creator,
        )

    async def _resolve_mind_lens(
        self, execution_plan: ExecutionPlan, ctx: LocalDomainContext
    ) -> None:
        """
        Resolve Mind Lens if not already set

        Mind Lens is a Cloud extension, accessed via API.

        Args:
            execution_plan: Execution plan
            ctx: Execution context
        """
        if ctx.mind_lens is not None:
            return

        try:
            import os
            import httpx

            cloud_api_url = os.getenv("CLOUD_API_URL")
            if cloud_api_url:
                playbook_id = None
                if execution_plan.tasks:
                    first_task = execution_plan.tasks[0]
                    playbook_id = getattr(first_task, "playbook_id", None)

                # Call Cloud API to resolve Mind Lens
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{cloud_api_url}/mind-lens/resolve",
                        json={
                            "user_id": ctx.actor_id,
                            "workspace_id": ctx.workspace_id,
                            "playbook_id": playbook_id,
                            "role_hint": None,
                        },
                        timeout=5.0,
                    )
                    if response.status_code == 200:
                        ctx.mind_lens = response.json()
        except Exception as e:
            # Mind Lens not available, continue without it
            logger.debug(f"Mind Lens not available: {e}")


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
        """
        Execute readonly task automatically

        Uses new coordination modules where possible, falls back to legacy handlers for special packs.
        """
        pack_id = task_plan.pack_id
        pack_id_lower = pack_id.lower() if pack_id else ""

        # Special handling for intent_extraction
        if pack_id_lower == "intent_extraction":
            logger.error(
                f"CoordinatorFacade: intent_extraction should not reach _execute_readonly_task. "
                f"This indicates a routing issue. Task should be handled by IntentInfraService."
            )
            raise ValueError(
                f"intent_extraction should be handled by IntentInfraService, not CoordinatorFacade."
            )

        # Handle hardcoded pack executors first (for backward compatibility)
        if pack_id == "semantic_seeds":
            return await self.special_pack_executors.execute_semantic_seeds(
                workspace_id=ctx.workspace_id,
                profile_id=ctx.actor_id,
                message_id=message_id,
                files=files,
                message=message,
                event_emitter=event_emitter,
            )

        # Check execution method: PlaybookService handles playbooks, CapabilityRegistry handles capability packs
        execution_method = None

        # Check PlaybookService first
        if self.playbook_service:
            try:
                playbook = await self.playbook_service.get_playbook(
                    playbook_code=pack_id,
                    locale=self.default_locale,
                    workspace_id=ctx.workspace_id,
                )
                if playbook:
                    execution_method = "playbook"
                    logger.info(
                        f"CoordinatorFacade: Pack {pack_id} found in PlaybookService, execution method: {execution_method}"
                    )
            except Exception as e:
                logger.warning(
                    f"CoordinatorFacade: Playbook {pack_id} error in PlaybookService: {type(e).__name__}: {e}"
                )

        # If not a playbook, check CapabilityRegistry for pack_executor
        if not execution_method:
            from ...capabilities.registry import get_registry

            registry = get_registry()
            execution_method = registry.get_execution_method(pack_id)
            logger.info(
                f"CoordinatorFacade: Pack {pack_id} execution method from CapabilityRegistry: {execution_method}"
            )

        # Use new coordination modules for playbook-based execution
        if execution_method == "playbook":
            # Prepare plan using PlanPreparer
            prepared_plan = await self.plan_preparer.prepare_plan(
                task_plan=task_plan,
                ctx=ctx,
                message_id=message_id,
                files=files,
                message=message,
                project_id=project_id,
            )

            # Resolve playbook code using PlaybookResolver
            resolved_playbook = await self.playbook_resolver.resolve(
                pack_id=prepared_plan.pack_id, ctx=ctx
            )

            if not resolved_playbook:
                self.error_policy.warn_and_continue(
                    f"Could not resolve playbook for pack {pack_id}"
                )
                return None

            # Launch execution using ExecutionLauncher
            try:
                launch_result = await self.execution_launcher.launch(
                    playbook_code=resolved_playbook.code,
                    inputs=prepared_plan.playbook_inputs,
                    ctx=ctx,
                    project_meta=prepared_plan.project_meta,
                    project_id=project_id,
                )

                execution_id = launch_result.get("execution_id")
                if not execution_id:
                    self.error_policy.handle_missing_execution_id(
                        resolved_playbook.code, launch_result.get("raw_result")
                    )

                # Emit task created event
                if execution_id:
                    task = self.tasks_store.get_task_by_execution_id(execution_id)
                    if task:
                        event_emitter.emit_task_created(
                            task_id=task.id,
                            pack_id=pack_id,
                            playbook_code=resolved_playbook.code,
                            status=task.status.value
                            if hasattr(task.status, "value")
                            else str(task.status),
                            task_type=task.task_type,
                            workspace_id=ctx.workspace_id,
                            execution_id=execution_id,
                        )
                    elif execution_id:
                        event_emitter.emit_task_created(
                            task_id=execution_id,
                            pack_id=pack_id,
                            playbook_code=resolved_playbook.code,
                            status="running",
                            task_type="playbook_execution",
                            workspace_id=ctx.workspace_id,
                            execution_id=execution_id,
                        )

                return {
                    "pack_id": pack_id,
                    "playbook_code": resolved_playbook.code,
                    "execution_id": execution_id,
                }

            except Exception as e:
                self.error_policy.handle_execution_error(
                    f"launch playbook {resolved_playbook.code}", e, raise_on_error=True
                )

        elif execution_method == "pack_executor":
            self.error_policy.warn_and_continue(
                f"Pack {pack_id} has pack_executor but no handler in CoordinatorFacade"
            )
            return None

        self.error_policy.warn_and_continue(
            f"Unknown execution method for pack {pack_id}: {execution_method}"
        )
        return None

    async def execute_playbook(
        self,
        playbook_code: str,
        playbook_context: Dict[str, Any],
        workspace_id: str,
        profile_id: str,
        message_id: str,
        project_id: Optional[str],
    ) -> Dict[str, Any]:
        """
        Execute playbook based on side_effect_level

        Args:
            playbook_code: Playbook code
            playbook_context: Playbook context
            workspace_id: Workspace ID
            profile_id: User profile ID
            message_id: Message/event ID
            project_id: Optional project ID

        Returns:
            Dict with execution result
        """
        ctx = LocalDomainContext(
            actor_id=profile_id, workspace_id=workspace_id, tags={"mode": "local"}
        )
        return await self.create_execution_with_ctx(
            playbook_code=playbook_code,
            playbook_context=playbook_context,
            ctx=ctx,
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
        """
        Create execution based on side_effect_level and from_suggestion_action flag

        Args:
            playbook_code: Playbook code
            playbook_context: Playbook context (may contain from_suggestion_action flag)
            ctx: Execution context
            message_id: Message/event ID
            project_id: Optional project ID

        Returns:
            Dict with execution result (status: "started" or "suggestion")
        """
        side_effect_level = self.plan_builder.determine_side_effect_level(playbook_code)

        from_suggestion_action = playbook_context.get("from_suggestion_action", False)

        logger.info(
            f"CoordinatorFacade.create_execution_with_ctx: playbook={playbook_code}, "
            f"side_effect_level={side_effect_level}, from_suggestion_action={from_suggestion_action}"
        )

        event_emitter = TaskEventsEmitter()

        if from_suggestion_action:
            logger.info(
                f"CoordinatorFacade: Executing playbook {playbook_code} directly (user confirmed from suggestion)"
            )
            result = await self._execute_readonly_playbook(
                playbook_code=playbook_code,
                playbook_context=playbook_context,
                ctx=ctx,
                message_id=message_id,
                project_id=project_id,
                event_emitter=event_emitter,
            )
            return {
                "status": "started",
                "execution_id": result.get("execution_id"),
                "task_id": result.get("task_id"),
            }
        elif side_effect_level == SideEffectLevel.READONLY:
            logger.info(
                f"CoordinatorFacade: Executing READONLY playbook {playbook_code} directly"
            )
            result = await self._execute_readonly_playbook(
                playbook_code=playbook_code,
                playbook_context=playbook_context,
                ctx=ctx,
                message_id=message_id,
                project_id=project_id,
                event_emitter=event_emitter,
            )
            return {
                "status": "started",
                "execution_id": result.get("execution_id"),
                "task_id": result.get("task_id"),
            }
        else:
            logger.info(
                f"CoordinatorFacade: Creating suggestion card for {side_effect_level} playbook {playbook_code}"
            )
            result = await self.suggestion_card_creator.create_playbook_suggestion(
                playbook_code=playbook_code,
                playbook_context=playbook_context,
                workspace_id=ctx.workspace_id,
                message_id=message_id,
                event_emitter=event_emitter,
            )
            return {
                "status": "suggestion",
                "task_id": result.get("task_id"),
            }

    async def _execute_readonly_playbook(
        self,
        playbook_code: str,
        playbook_context: Dict[str, Any],
        ctx: LocalDomainContext,
        message_id: str,
        project_id: Optional[str],
        event_emitter: TaskEventsEmitter,
    ) -> Dict[str, Any]:
        """
        Execute readonly playbook automatically

        Uses ExecutionLauncher for playbook execution, then handles task creation and event emission.
        """
        try:
            # Prepare inputs
            playbook_inputs = playbook_context.copy()
            playbook_inputs["workspace_id"] = ctx.workspace_id

            # Load project metadata if project_id is provided
            project_meta = None
            if project_id:
                project_meta = await self.plan_preparer._load_project_meta(
                    project_id, ctx.workspace_id
                )
                if project_meta:
                    playbook_inputs = self.execution_launcher._ensure_project_metadata(
                        playbook_inputs, project_meta
                    )

            # Launch execution using ExecutionLauncher
            launch_result = await self.execution_launcher.launch(
                playbook_code=playbook_code,
                inputs=playbook_inputs,
                ctx=ctx,
                project_meta=project_meta,
                project_id=project_id,
            )

            execution_result = launch_result.get("raw_result")
            execution_id = launch_result.get("execution_id")
            execution_mode = launch_result.get("execution_mode", "conversation")

            if not execution_id:
                self.error_policy.handle_missing_execution_id(
                    playbook_code, execution_result
                )

            from ...services.i18n_service import get_i18n_service

            i18n = get_i18n_service(default_locale=self.default_locale)

            if execution_mode == "workflow":
                assistant_response = i18n.t(
                    "conversation_orchestrator",
                    "workflow.started",
                    playbook_code=playbook_code,
                    default=f"Started workflow execution for {playbook_code}",
                )
            else:
                assistant_response = execution_result.get("result", {}).get(
                    "message",
                    i18n.t(
                        "conversation_orchestrator",
                        "workflow.started",
                        playbook_code=playbook_code,
                        default=f"Started execution for {playbook_code}",
                    ),
                )

            assistant_event = MindEvent(
                id=str(uuid.uuid4()),
                timestamp=datetime.utcnow(),
                actor=EventActor.ASSISTANT,
                channel="local_workspace",
                profile_id=ctx.actor_id,
                project_id=project_id,
                workspace_id=ctx.workspace_id,
                event_type=EventType.MESSAGE,
                payload={
                    "message": assistant_response,
                    "response_to": message_id,
                    "playbook_code": playbook_code,
                },
                entity_ids=[],
                metadata={},
            )
            self.store.create_event(assistant_event)

            # Create or get task using TaskCreator
            task = await self.task_creator.create_or_get_task(
                playbook_code=playbook_code,
                playbook_context=playbook_context,
                ctx=ctx,
                message_id=message_id,
                execution_id=execution_id,
                execution_result=execution_result,
                execution_mode=execution_mode,
            )

            # Emit task created event
            event_emitter.emit_task_created(
                task_id=task.id,
                pack_id=playbook_code,
                status=task.status.value
                if hasattr(task.status, "value")
                else str(task.status),
                task_type=task.task_type,
                workspace_id=ctx.workspace_id,
            )

            await self.task_manager.check_and_update_task_status(
                task=task, execution_id=execution_id, playbook_code=playbook_code
            )

            return {
                "status": "started",
                "playbook_code": playbook_code,
                "execution_id": execution_id,
                "task_id": task.id,
                "message": assistant_response,
            }

        except Exception as e:
            self.error_policy.handle_execution_error(f"start playbook {playbook_code}", e)
            from ...services.i18n_service import get_i18n_service

            i18n = get_i18n_service(default_locale=self.default_locale)
            return {
                "status": "failed",
                "playbook_code": playbook_code,
                "error": str(e),
                "message": i18n.t(
                    "conversation_orchestrator",
                    "workflow.failed",
                    playbook_code=playbook_code,
                    error=str(e),
                ),
            }


