"""
Playbook Run Executor
Unified executor for playbook.run = playbook.md + playbook.json

Automatically selects execution mode based on available components:
- If playbook.json exists: use WorkflowOrchestrator (structured workflow)
- If only playbook.md exists: use PlaybookRunner (LLM conversation)

DEPRECATED: Legacy playbook execution, scheduled for removal after P2.
Do not add new dependencies. Use PlaybookService.execute_playbook() instead.
This class is only used internally by PlaybookService for backward compatibility.
"""

import logging
from typing import Dict, Any, Optional

from backend.app.models.playbook import (
    PlaybookRun,
    PlaybookKind,
    PlaybookInvocationContext,
    InvocationMode,
    InvocationStrategy,
    InvocationTolerance
)
from backend.app.services.playbook_runner import PlaybookRunner
from backend.app.services.workflow_orchestrator import WorkflowOrchestrator
from backend.app.services.playbook_service import PlaybookService
from backend.app.services.playbook_initializer import PlaybookInitializer
from backend.app.services.playbook_checkpoint_manager import PlaybookCheckpointManager
from backend.app.services.playbook_phase_manager import PlaybookPhaseManager
from backend.app.services.stores.playbook_executions_store import PlaybookExecutionsStore
from backend.app.models.execution_metadata import ExecutionMetadata
from backend.app.models.workspace import PlaybookExecution
from backend.app.services.runtime.runtime_factory import RuntimeFactory
from backend.app.services.runtime.simple_runtime import SimpleRuntime
from backend.app.core.runtime_port import ExecutionProfile
from backend.app.core.execution_context import ExecutionContext

logger = logging.getLogger(__name__)


class PlaybookRunExecutor:
    """Unified executor for playbook.run"""

    def __init__(self, store=None):
        """
        Initialize PlaybookRunExecutor

        Args:
            store: MindscapeStore instance (optional)
        """
        self.store = store
        self.playbook_runner = PlaybookRunner()

        if store:
            self.workflow_orchestrator = WorkflowOrchestrator(store=store)
            mindscape_store = store
        else:
            from backend.app.services.mindscape_store import MindscapeStore
            mindscape_store = MindscapeStore()
            self.workflow_orchestrator = WorkflowOrchestrator(store=mindscape_store)

        self.playbook_service = PlaybookService(store=mindscape_store)

        # Initialize Claude-style long-chain execution components
        db_path = mindscape_store.db_path if hasattr(mindscape_store, 'db_path') else None
        if db_path:
            self.executions_store = PlaybookExecutionsStore(db_path)
            self.checkpoint_manager = PlaybookCheckpointManager(self.executions_store)
            self.phase_manager = PlaybookPhaseManager(self.executions_store, None)  # Events store TBD
        else:
            self.executions_store = None
            self.checkpoint_manager = None
            self.phase_manager = None

        # Initialize initializer for first-time playbook execution
        self.initializer = PlaybookInitializer("/tmp/mindscape-workspace")  # Configurable path

        # Initialize runtime factory
        self.runtime_factory = RuntimeFactory()

        # Register default runtime (SimpleRuntime wraps WorkflowOrchestrator)
        simple_runtime = SimpleRuntime(store=mindscape_store)
        self.runtime_factory.register_runtime(simple_runtime, is_default=True)

        # Try to load runtime providers from capability packs
        self._load_runtime_providers()

    async def execute_playbook_run(
        self,
        playbook_code: str,
        profile_id: str,
        inputs: Optional[Dict[str, Any]] = None,
        workspace_id: Optional[str] = None,
        project_id: Optional[str] = None,
        target_language: Optional[str] = None,
        variant_id: Optional[str] = None,
        locale: Optional[str] = None,
        context: Optional[PlaybookInvocationContext] = None
    ) -> Dict[str, Any]:
        """
        Execute playbook.run with appropriate runtime

        Args:
            playbook_code: Playbook code
            profile_id: User profile ID
            inputs: Execution inputs
            workspace_id: Optional workspace ID (required for multi-turn conversations)
            project_id: Optional project ID for sandbox context
            target_language: Target language for output
            variant_id: Optional personalized variant ID
            locale: Preferred locale for playbook.md
            context: Optional invocation context (if None, uses legacy behavior)

        Returns:
            Execution result dict
        """
        playbook_run = await self.playbook_service.load_playbook_run(
            playbook_code=playbook_code,
            locale=locale or 'zh-TW',
            workspace_id=workspace_id
        )

        if not playbook_run:
            raise ValueError(f"Playbook not found: {playbook_code}")

        execution_mode = playbook_run.get_execution_mode()
        logger.info(f"PlaybookRunExecutor: playbook_code={playbook_code}, execution_mode={execution_mode}, has_json={playbook_run.has_json()}, context_mode={context.mode if context else None}")

        if context and context.mode != InvocationMode.SUBROUTINE:
            if context.mode == InvocationMode.STANDALONE:
                return await self._handle_standalone(
                    playbook_run=playbook_run,
                    playbook_code=playbook_code,
                    profile_id=profile_id,
                    inputs=inputs,
                    workspace_id=workspace_id,
                    project_id=project_id,
                    target_language=target_language,
                    variant_id=variant_id,
                    locale=locale,
                    context=context
                )
            elif context.mode == InvocationMode.PLAN_NODE:
                return await self._handle_plan_node(
                    playbook_run=playbook_run,
                    playbook_code=playbook_code,
                    profile_id=profile_id,
                    inputs=inputs,
                    workspace_id=workspace_id,
                    project_id=project_id,
                    target_language=target_language,
                    variant_id=variant_id,
                    locale=locale,
                    context=context
                )

        if execution_mode == 'workflow' and playbook_run.playbook_json:
            logger.info(f"PlaybookRunExecutor: Executing {playbook_code} using Runtime system (playbook.json found)")

            if not workspace_id:
                error_msg = f"workspace_id is required for playbook execution: {playbook_code}"
                logger.error(f"PlaybookRunExecutor: {error_msg}")
                raise ValueError(error_msg)

            # Get execution profile from playbook
            execution_profile = playbook_run.get_execution_profile()

            # Select runtime based on execution profile
            runtime = self.runtime_factory.get_runtime(execution_profile)
            logger.info(f"PlaybookRunExecutor: Selected runtime: {runtime.name} for playbook {playbook_code}")

            # Create execution context
            import uuid
            from datetime import datetime
            execution_id = str(uuid.uuid4())

            exec_context = ExecutionContext(
                actor_id=profile_id,
                workspace_id=workspace_id,
                tags={
                    "execution_id": execution_id,
                    "playbook_code": playbook_code,
                    "project_id": project_id or ""
                }
            )

            # Execute using selected runtime
            try:
                runtime_result = await runtime.execute(
                    playbook_run=playbook_run,
                    context=exec_context,
                    inputs=inputs
                )

                # Convert ExecutionResult to legacy format for backward compatibility
                # Extract steps from metadata if available
                steps_from_metadata = runtime_result.metadata.get("steps", {})
                result = {
                    "status": runtime_result.status,
                    "context": runtime_result.outputs,
                    "steps": steps_from_metadata  # Use actual steps from metadata
                }

                # Update task status if using task system
                if execution_profile.execution_mode == "simple":
                    # For simple mode, use existing task system
                    from backend.app.services.stores.tasks_store import TasksStore
                    from backend.app.services.mindscape_store import MindscapeStore
                    from backend.app.models.workspace import Task, TaskStatus

                    store = MindscapeStore()
                    tasks_store = TasksStore(store.db_path)
                    total_steps = len(playbook_run.playbook_json.steps) if playbook_run.playbook_json.steps else 1

                    execution_context_dict = {
                        "playbook_code": playbook_code,
                        "playbook_name": playbook_run.playbook.metadata.name,
                        "execution_id": execution_id,
                        "total_steps": total_steps,
                        "current_step_index": total_steps if runtime_result.status == "completed" else 0,
                        "status": runtime_result.status,
                    }

                    task = Task(
                        id=execution_id,
                        workspace_id=workspace_id,
                        message_id=str(uuid.uuid4()),
                        execution_id=execution_id,
                        profile_id=profile_id,
                        pack_id=playbook_code,
                        task_type="playbook_execution",
                        status=TaskStatus.SUCCEEDED if runtime_result.status == "completed" else TaskStatus.FAILED,
                        execution_context=execution_context_dict,
                        created_at=datetime.utcnow(),
                        started_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                        completed_at=datetime.utcnow() if runtime_result.status == "completed" else None,
                        error=runtime_result.error
                    )
                    tasks_store.create_task(task)

                return {
                    "execution_mode": "workflow",
                    "playbook_code": playbook_code,
                    "execution_id": execution_id,
                    "result": result,
                    "has_json": True,
                    "runtime": runtime.name
                }

            except Exception as e:
                logger.error(f"PlaybookRunExecutor: Runtime execution failed: {e}", exc_info=True)
                raise

        else:
            logger.info(f"Executing {playbook_code} using PlaybookRunner (LLM conversation mode), workspace_id={workspace_id}, project_id={project_id}")

            result = await self.playbook_runner.start_playbook_execution(
                playbook_code=playbook_code,
                profile_id=profile_id,
                inputs=inputs,
                workspace_id=workspace_id,
                project_id=project_id,
                target_language=target_language,
                variant_id=variant_id
            )

            return {
                "execution_mode": "conversation",
                "playbook_code": playbook_code,
                "result": result,
                "has_json": False
            }

    async def get_playbook_run(self, playbook_code: str, locale: Optional[str] = None) -> Optional[PlaybookRun]:
        """
        Get playbook.run definition without executing

        Args:
            playbook_code: Playbook code
            locale: Preferred locale

        Returns:
            PlaybookRun or None if not found
        """
        return await self.playbook_service.load_playbook_run(
            playbook_code=playbook_code,
            locale=locale or 'zh-TW',
            workspace_id=None
        )

    async def _handle_standalone(
        self,
        playbook_run: PlaybookRun,
        playbook_code: str,
        profile_id: str,
        inputs: Optional[Dict[str, Any]],
        workspace_id: Optional[str],
        project_id: Optional[str],
        target_language: Optional[str],
        variant_id: Optional[str],
        locale: Optional[str],
        context: PlaybookInvocationContext
    ) -> Dict[str, Any]:
        """
        Handle standalone execution strategy

        Standalone mode allows multiple lookup rounds and adaptive query refinement.
        The playbook can search for data multiple times, adjust queries, and combine results.

        Args:
            playbook_run: Playbook run definition
            playbook_code: Playbook code
            profile_id: User profile ID
            inputs: Execution inputs
            workspace_id: Workspace ID
            project_id: Optional project ID
            target_language: Target language
            variant_id: Optional variant ID
            locale: Locale
            context: Invocation context

        Returns:
            Execution result dict
        """
        logger.info(
            f"PlaybookRunExecutor: Executing {playbook_code} in STANDALONE mode "
            f"(max_lookup_rounds={context.strategy.max_lookup_rounds})"
        )

        execution_mode = playbook_run.get_execution_mode()

        if execution_mode == 'workflow' and playbook_run.playbook_json:
            return await self._execute_workflow_standalone(
                playbook_run=playbook_run,
                playbook_code=playbook_code,
                profile_id=profile_id,
                inputs=inputs,
                workspace_id=workspace_id,
                project_id=project_id,
                context=context
            )
        else:
            return await self._execute_conversation_standalone(
                playbook_run=playbook_run,
                playbook_code=playbook_code,
                profile_id=profile_id,
                inputs=inputs,
                workspace_id=workspace_id,
                project_id=project_id,
                target_language=target_language,
                variant_id=variant_id,
                context=context
            )

    async def _handle_plan_node(
        self,
        playbook_run: PlaybookRun,
        playbook_code: str,
        profile_id: str,
        inputs: Optional[Dict[str, Any]],
        workspace_id: Optional[str],
        project_id: Optional[str],
        target_language: Optional[str],
        variant_id: Optional[str],
        locale: Optional[str],
        context: PlaybookInvocationContext
    ) -> Dict[str, Any]:
        """
        Handle plan node execution strategy

        Plan node mode uses only the data provided by the plan.
        It does not perform additional lookups and reports errors if plan data is insufficient.

        Args:
            playbook_run: Playbook run definition
            playbook_code: Playbook code
            profile_id: User profile ID
            inputs: Execution inputs (may contain plan-provided data)
            workspace_id: Workspace ID
            project_id: Optional project ID
            target_language: Target language
            variant_id: Optional variant ID
            locale: Locale
            context: Invocation context

        Returns:
            Execution result dict

        Raises:
            ValueError: If plan data is insufficient and tolerance is strict
        """
        logger.info(
            f"PlaybookRunExecutor: Executing {playbook_code} in PLAN_NODE mode "
            f"(plan_id={context.plan_id}, task_id={context.task_id})"
        )

        if context.plan_context:
            logger.info(
                f"PlaybookRunExecutor: Plan context available - "
                f"summary={context.plan_context.plan_summary[:100] if context.plan_context.plan_summary else 'N/A'}, "
                f"dependencies={context.plan_context.dependencies}"
            )

        plan_data = None
        if context.visible_state:
            plan_data = context.visible_state.get('fromPlan') or context.visible_state.get('plan_data')

        if not plan_data and context.strategy.tolerance == InvocationTolerance.STRICT:
            error_msg = (
                f"Plan input insufficient for playbook {playbook_code}. "
                f"Required data not provided by upstream tasks."
            )
            logger.error(f"PlaybookRunExecutor: {error_msg}")
            raise ValueError(error_msg)

        if plan_data:
            inputs = inputs or {}
            inputs.update(plan_data)
            logger.info(f"PlaybookRunExecutor: Merged plan data into inputs for {playbook_code}")

        if context.strategy.wait_for_upstream_tasks and context.plan_context:
            dependencies = context.plan_context.dependencies
            if dependencies:
                logger.info(
                    f"PlaybookRunExecutor: Waiting for upstream tasks: {dependencies}"
                )
                # Upstream task waiting logic to be implemented

        execution_mode = playbook_run.get_execution_mode()

        if execution_mode == 'workflow' and playbook_run.playbook_json:
            return await self._execute_workflow_plan_node(
                playbook_run=playbook_run,
                playbook_code=playbook_code,
                profile_id=profile_id,
                inputs=inputs,
                workspace_id=workspace_id,
                project_id=project_id,
                context=context
            )
        else:
            return await self._execute_conversation_plan_node(
                playbook_run=playbook_run,
                playbook_code=playbook_code,
                profile_id=profile_id,
                inputs=inputs,
                workspace_id=workspace_id,
                project_id=project_id,
                target_language=target_language,
                variant_id=variant_id,
                context=context
            )

    async def _execute_workflow_standalone(
        self,
        playbook_run: PlaybookRun,
        playbook_code: str,
        profile_id: str,
        inputs: Optional[Dict[str, Any]],
        workspace_id: Optional[str],
        project_id: Optional[str],
        context: PlaybookInvocationContext
    ) -> Dict[str, Any]:
        """Execute workflow in standalone mode"""
        return await self._execute_workflow_legacy(
            playbook_run=playbook_run,
            playbook_code=playbook_code,
            profile_id=profile_id,
            inputs=inputs,
            workspace_id=workspace_id,
            project_id=project_id
        )

    async def _execute_conversation_standalone(
        self,
        playbook_run: PlaybookRun,
        playbook_code: str,
        profile_id: str,
        inputs: Optional[Dict[str, Any]],
        workspace_id: Optional[str],
        project_id: Optional[str],
        target_language: Optional[str],
        variant_id: Optional[str],
        context: PlaybookInvocationContext
    ) -> Dict[str, Any]:
        """Execute conversation in standalone mode with multi-round lookup support"""
        logger.info(
            f"PlaybookRunExecutor: Executing conversation in standalone mode "
            f"(max_lookup_rounds={context.strategy.max_lookup_rounds})"
        )

        result = await self.playbook_runner.start_playbook_execution(
            playbook_code=playbook_code,
            profile_id=profile_id,
            inputs=inputs,
            workspace_id=workspace_id,
            project_id=project_id,
            target_language=target_language,
            variant_id=variant_id
        )

        return {
            "execution_mode": "conversation",
            "playbook_code": playbook_code,
            "result": result,
            "has_json": False,
            "invocation_mode": "standalone"
        }

    async def _execute_workflow_plan_node(
        self,
        playbook_run: PlaybookRun,
        playbook_code: str,
        profile_id: str,
        inputs: Optional[Dict[str, Any]],
        workspace_id: Optional[str],
        project_id: Optional[str],
        context: PlaybookInvocationContext
    ) -> Dict[str, Any]:
        """Execute workflow in plan_node mode"""
        return await self._execute_workflow_legacy(
            playbook_run=playbook_run,
            playbook_code=playbook_code,
            profile_id=profile_id,
            inputs=inputs,
            workspace_id=workspace_id,
            project_id=project_id
        )

    async def _execute_conversation_plan_node(
        self,
        playbook_run: PlaybookRun,
        playbook_code: str,
        profile_id: str,
        inputs: Optional[Dict[str, Any]],
        workspace_id: Optional[str],
        project_id: Optional[str],
        target_language: Optional[str],
        variant_id: Optional[str],
        context: PlaybookInvocationContext
    ) -> Dict[str, Any]:
        """Execute conversation in plan_node mode using only plan-provided data"""
        logger.info(
            f"PlaybookRunExecutor: Executing conversation in plan_node mode "
            f"(plan_id={context.plan_id}, task_id={context.task_id})"
        )

        result = await self.playbook_runner.start_playbook_execution(
            playbook_code=playbook_code,
            profile_id=profile_id,
            inputs=inputs,
            workspace_id=workspace_id,
            project_id=project_id,
            target_language=target_language,
            variant_id=variant_id
        )

        return {
            "execution_mode": "conversation",
            "playbook_code": playbook_code,
            "result": result,
            "has_json": False,
            "invocation_mode": "plan_node",
            "plan_id": context.plan_id,
            "task_id": context.task_id
        }

    async def _execute_workflow_legacy(
        self,
        playbook_run: PlaybookRun,
        playbook_code: str,
        profile_id: str,
        inputs: Optional[Dict[str, Any]],
        workspace_id: Optional[str],
        project_id: Optional[str]
    ) -> Dict[str, Any]:
        """Legacy workflow execution (extracted for reuse)"""
        if not workspace_id:
            error_msg = f"workspace_id is required for playbook execution: {playbook_code}"
            logger.error(f"PlaybookRunExecutor: {error_msg}")
            raise ValueError(error_msg)

        import uuid
        from datetime import datetime
        from backend.app.services.stores.tasks_store import TasksStore
        from backend.app.services.mindscape_store import MindscapeStore
        from backend.app.models.workspace import Task, TaskStatus

        execution_id = str(uuid.uuid4())
        store = MindscapeStore()
        tasks_store = TasksStore(store.db_path)
        total_steps = len(playbook_run.playbook_json.steps) if playbook_run.playbook_json.steps else 1

        execution_metadata = ExecutionMetadata()
        execution_metadata.set_execution_context(playbook_code=playbook_code)

        if self.executions_store:
            execution_record = PlaybookExecution(
                id=execution_id,
                workspace_id=workspace_id,
                playbook_code=playbook_code,
                intent_instance_id=None,
                status="running",
                phase="initialization",
                last_checkpoint=None,
                progress_log_path=None,
                feature_list_path=None,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            self.executions_store.create_execution(execution_record)

            init_result = await self.initializer.initialize_playbook_execution(
                execution_id=execution_record.id,
                playbook_code=playbook_code,
                workspace_id=workspace_id
            )

            if init_result["success"]:
                execution_record.progress_log_path = init_result["artifacts"].get("progress_log")
                execution_record.feature_list_path = init_result["artifacts"].get("feature_list")
                self.executions_store.update_execution_status(
                    execution_id=execution_record.id,
                    status="running",
                    phase="execution"
                )

        execution_context = {
            "playbook_code": playbook_code,
            "playbook_name": playbook_run.playbook.metadata.name,
            "execution_id": execution_id,
            "total_steps": total_steps,
            "current_step_index": 0,
            "status": "running",
            "execution_metadata": execution_metadata.to_dict()
        }

        task = Task(
            id=execution_id,
            workspace_id=workspace_id,
            message_id=str(uuid.uuid4()),
            execution_id=execution_id,
            profile_id=profile_id,
            pack_id=playbook_code,
            task_type="playbook_execution",
            status=TaskStatus.RUNNING,
            execution_context=execution_context,
            created_at=datetime.utcnow(),
            started_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        tasks_store.create_task(task)

        from backend.app.models.playbook import HandoffPlan, WorkflowStep

        workflow_step = WorkflowStep(
            playbook_code=playbook_code,
            kind=playbook_run.playbook_json.kind,
            inputs=inputs or {},
            interaction_mode=playbook_run.playbook.metadata.interaction_mode
        )

        handoff_plan = HandoffPlan(
            steps=[workflow_step],
            context=inputs or {}
        )

        try:
            result = await self.workflow_orchestrator.execute_workflow(
                handoff_plan,
                execution_id=execution_id,
                workspace_id=workspace_id,
                profile_id=profile_id
            )

            execution_context["status"] = "completed"
            execution_context["current_step_index"] = total_steps
            completed_at = datetime.utcnow()
            tasks_store.update_task(
                task.id,
                execution_context=execution_context,
                status=TaskStatus.SUCCEEDED,
                completed_at=completed_at
            )
            logger.info(f"PlaybookRunExecutor: Execution {execution_id} completed successfully")
        except Exception as e:
            from backend.app.shared.error_handler import parse_api_error

            error_info = parse_api_error(e)
            execution_context["status"] = "failed"
            execution_context["error"] = error_info.user_message
            execution_context["error_details"] = error_info.to_dict()
            completed_at = datetime.utcnow()
            tasks_store.update_task(
                task.id,
                execution_context=execution_context,
                status=TaskStatus.FAILED,
                completed_at=completed_at,
                error=error_info.user_message
            )
            logger.error(f"PlaybookRunExecutor: Execution {execution_id} failed: {e}")
            raise

        return {
            "execution_mode": "workflow",
            "playbook_code": playbook_code,
            "execution_id": execution_id,
            "result": result,
            "has_json": True
        }

    def _load_runtime_providers(self):
        """
        Dynamically load runtime providers from capability packs

        Scans installed capability packs for runtime providers (type: system_runtime)
        and registers them with the RuntimeFactory.
        """
        try:
            from backend.app.services.runtime.capability_runtime_loader import CapabilityRuntimeLoader

            loader = CapabilityRuntimeLoader()
            loaded_runtimes = loader.load_all_runtime_providers()

            for runtime in loaded_runtimes:
                self.runtime_factory.register_runtime(runtime)
                logger.info(f"Registered runtime provider: {runtime.name}")

            if loaded_runtimes:
                logger.info(f"Loaded {len(loaded_runtimes)} runtime provider(s) from capability packs")
            else:
                logger.debug("No runtime providers found in capability packs")

        except Exception as e:
            logger.warning(f"Failed to load runtime providers: {e}", exc_info=True)

