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
from backend.app.core.domain_context import LocalDomainContext

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
        context: Optional[PlaybookInvocationContext] = None,
        execution_profile: Optional["ExecutionProfile"] = None  # New parameter
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

        # If no project_id provided, use workspace.primary_project_id as fallback
        if not project_id and workspace_id:
            try:
                from backend.app.services.mindscape_store import MindscapeStore
                store = MindscapeStore()
                workspace = store.get_workspace(workspace_id)
                if workspace and hasattr(workspace, 'primary_project_id') and workspace.primary_project_id:
                    project_id = workspace.primary_project_id
                    logger.info(f"PlaybookRunExecutor: Using workspace.primary_project_id={project_id} for playbook {playbook_code}")
            except Exception as e:
                logger.warning(f"PlaybookRunExecutor: Failed to get workspace.primary_project_id: {e}")

        # Normalize inputs and inject execution context fields for template resolution and tool parameters
        # This ensures {{input.workspace_id}}, {{input.project_id}}, {{input.profile_id}} templates can be resolved
        # and these fields are available for tool parameter injection
        normalized_inputs = inputs.copy() if inputs else {}
        if workspace_id and "workspace_id" not in normalized_inputs:
            normalized_inputs["workspace_id"] = workspace_id
        if project_id and "project_id" not in normalized_inputs:
            normalized_inputs["project_id"] = project_id
        if profile_id and "profile_id" not in normalized_inputs:
            normalized_inputs["profile_id"] = profile_id
        logger.info(f"PlaybookRunExecutor: normalized_inputs keys={list(normalized_inputs.keys())}")

        execution_mode = playbook_run.get_execution_mode()
        logger.info(f"PlaybookRunExecutor: playbook_code={playbook_code}, execution_mode={execution_mode}, has_json={playbook_run.has_json()}, context_mode={context.mode if context else None}, project_id={project_id}")

        if context and context.mode != InvocationMode.SUBROUTINE:
            if context.mode == InvocationMode.STANDALONE:
                return await self._handle_standalone(
                    playbook_run=playbook_run,
                    playbook_code=playbook_code,
                    profile_id=profile_id,
                    inputs=normalized_inputs,
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
                    inputs=normalized_inputs,
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

            logger.info(f"PlaybookRunExecutor: Creating LocalDomainContext with project_id={project_id}")
            exec_context = LocalDomainContext(
                actor_id=profile_id,
                workspace_id=workspace_id,
                tags={
                    "execution_id": execution_id,
                    "playbook_code": playbook_code,
                    "project_id": project_id or ""
                }
            )
            logger.info(f"PlaybookRunExecutor: LocalDomainContext.tags.project_id={exec_context.tags.get('project_id') if exec_context.tags else 'None'}")

            # Execute using selected runtime
            try:
                runtime_result = await runtime.execute(
                    playbook_run=playbook_run,
                    context=exec_context,
                    inputs=normalized_inputs
                )

                # Convert ExecutionResult to legacy format for backward compatibility
                # Extract steps from metadata if available
                steps_from_metadata = {}
                if runtime_result and runtime_result.metadata:
                    steps_from_metadata = runtime_result.metadata.get("steps", {})
                result = {
                    "status": runtime_result.status if runtime_result else "failed",
                    "context": runtime_result.outputs if runtime_result else {},
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

                    playbook_name = playbook_run.playbook.metadata.name if playbook_run.playbook and playbook_run.playbook.metadata else playbook_code
                    execution_context_dict = {
                        "playbook_code": playbook_code,
                        "playbook_name": playbook_name,
                        "execution_id": execution_id,
                        "total_steps": total_steps,
                        "current_step_index": total_steps if runtime_result and runtime_result.status == "completed" else 0,
                        "status": runtime_result.status if runtime_result else "failed",
                    }

                    task = Task(
                        id=execution_id,
                        workspace_id=workspace_id,
                        message_id=str(uuid.uuid4()),
                        execution_id=execution_id,
                        project_id=project_id,  # Set project_id so sandbox can be created
                        profile_id=profile_id,
                        pack_id=playbook_code,
                        task_type="playbook_execution",
                        status=TaskStatus.SUCCEEDED if runtime_result and runtime_result.status == "completed" else TaskStatus.FAILED,
                        execution_context=execution_context_dict,
                        created_at=datetime.utcnow(),
                        started_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                        completed_at=datetime.utcnow() if runtime_result and runtime_result.status == "completed" else None,
                        error=runtime_result.error if runtime_result else "Runtime execution returned None"
                    )
                    tasks_store.create_task(task)

                    # Extract sandbox_id from runtime_result metadata and save to execution_context
                    logger.error(f"🔍 Checking runtime_result.metadata: {runtime_result.metadata if runtime_result else 'None'}")
                    sandbox_id = runtime_result.metadata.get('sandbox_id') if runtime_result and runtime_result.metadata else None
                    logger.error(f"🔍 sandbox_id from metadata: {sandbox_id}")
                    if not sandbox_id:
                        # Also check result.steps for sandbox_id (from _execute_playbook_steps return value)
                        steps_info = runtime_result.metadata.get("steps", {}) if runtime_result and runtime_result.metadata else {}
                        logger.error(f"🔍 Checking steps_info: {list(steps_info.keys())}")
                        for step_code, step_result in steps_info.items():
                            logger.error(f"🔍 step_code={step_code}, step_result keys: {list(step_result.keys()) if isinstance(step_result, dict) else 'not dict'}")
                            if isinstance(step_result, dict) and 'sandbox_id' in step_result:
                                sandbox_id = step_result['sandbox_id']
                                logger.error(f"🔍 Found sandbox_id in step_result: {sandbox_id}")
                                break

                    if sandbox_id:
                        logger.error(f"🔍 PlaybookRunExecutor: Saving sandbox_id={sandbox_id} to execution_context for execution {execution_id}")
                        execution_context_dict["sandbox_id"] = sandbox_id
                        tasks_store.update_task(task.id, execution_context=execution_context_dict)
                    else:
                        logger.error(f"🔍 No sandbox_id found to save")

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
                inputs=normalized_inputs,
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

        playbook_name = playbook_run.playbook.metadata.name if playbook_run.playbook and playbook_run.playbook.metadata else playbook_code
        execution_context = {
            "playbook_code": playbook_code,
            "playbook_name": playbook_name,
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
            project_id=project_id,  # Set project_id so sandbox can be created
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

        # Use normalized_inputs to ensure workspace_id/project_id/profile_id are available
        # Note: inputs parameter should already be normalized_inputs when called from _handle_standalone/_handle_plan_node
        # But we ensure it's normalized here as well for safety
        normalized_inputs_for_legacy = inputs.copy() if inputs else {}
        if workspace_id and "workspace_id" not in normalized_inputs_for_legacy:
            normalized_inputs_for_legacy["workspace_id"] = workspace_id
        if project_id and "project_id" not in normalized_inputs_for_legacy:
            normalized_inputs_for_legacy["project_id"] = project_id
        if profile_id and "profile_id" not in normalized_inputs_for_legacy:
            normalized_inputs_for_legacy["profile_id"] = profile_id
        logger.info(f"PlaybookRunExecutor._execute_workflow_legacy: normalized_inputs keys={list(normalized_inputs_for_legacy.keys())}")

        workflow_step = WorkflowStep(
            playbook_code=playbook_code,
            kind=playbook_run.playbook_json.kind,
            inputs=normalized_inputs_for_legacy,
            interaction_mode=playbook_run.playbook.metadata.interaction_mode if playbook_run.playbook and playbook_run.playbook.metadata else "conversational"
        )

        handoff_plan = HandoffPlan(
            steps=[workflow_step],
            context=normalized_inputs_for_legacy
        )

        try:
            result = await self.workflow_orchestrator.execute_workflow(
                handoff_plan,
                execution_id=execution_id,
                workspace_id=workspace_id,
                profile_id=profile_id,
                project_id=project_id
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
