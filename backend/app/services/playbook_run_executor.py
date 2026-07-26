"""Compatibility facade for playbook.run execution."""

import logging
import os
from typing import Dict, Any, Optional

from backend.app.models.playbook import (
    PlaybookRun,
    PlaybookInvocationContext,
    InvocationMode,
)
from backend.app.services.playbook_runner import PlaybookRunner
from backend.app.services.workflow_orchestrator import WorkflowOrchestrator
from backend.app.services.playbook_service import PlaybookService
from backend.app.services.playbook_initializer import PlaybookInitializer
from backend.app.services.playbook_checkpoint_manager import PlaybookCheckpointManager
from backend.app.services.playbook_phase_manager import PlaybookPhaseManager
from backend.app.services.playbook_run_executor_core.legacy_workflow import (
    execute_legacy_workflow as executor_execute_legacy_workflow,
)
from backend.app.services.playbook_run_executor_core.invocation_modes import (
    execute_conversation_invocation as executor_execute_conversation_invocation,
    merge_plan_node_inputs as executor_merge_plan_node_inputs,
)
from backend.app.services.playbook_run_executor_core.input_contract import (
    apply_playbook_input_contract as executor_apply_playbook_input_contract,
)
from backend.app.services.playbook_run_executor_core.remote_execution import (
    maybe_dispatch_remote_execution as executor_maybe_dispatch_remote_execution,
    normalize_execution_backend_hint as _normalize_execution_backend_hint,
)
from backend.app.services.playbook_run_executor_core.result_status import (
    runtime_result_has_errors as _runtime_result_has_errors,
    workflow_result_has_errors as _workflow_result_has_errors,
)
from backend.app.services.playbook_run_executor_core.runtime_provider_loading import (
    load_runtime_providers as executor_load_runtime_providers,
)
from backend.app.services.playbook_run_executor_core.runtime_workflow import (
    execute_runtime_workflow as executor_execute_runtime_workflow,
)
from backend.app.services.runtime.runtime_factory import RuntimeFactory
from backend.app.services.runtime.simple_runtime import SimpleRuntime

logger = logging.getLogger(__name__)


def _is_runner_process() -> bool:
    val = (os.getenv("LOCAL_CORE_RUNNER_PROCESS", "") or "").strip().lower()
    return val in {"1", "true", "yes"}


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
        self.executions_store = mindscape_store.playbook_executions
        self.checkpoint_manager = PlaybookCheckpointManager(self.executions_store)
        self.phase_manager = PlaybookPhaseManager(
            self.executions_store, None
        )  # Events store TBD

        # Initialize initializer for first-time playbook execution
        self.initializer = PlaybookInitializer(
            "/tmp/mindscape-workspace"
        )  # Configurable path

        # Initialize runtime factory
        self.runtime_factory = RuntimeFactory()

        # Register default runtime (SimpleRuntime wraps WorkflowOrchestrator)
        simple_runtime = SimpleRuntime(store=mindscape_store)
        self.runtime_factory.register_runtime(simple_runtime, is_default=True)

        # Try to load runtime providers from capability packs
        self._load_runtime_providers()

    @staticmethod
    def _apply_playbook_input_contract(
        playbook_code: str,
        playbook_run: PlaybookRun,
        inputs: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        return executor_apply_playbook_input_contract(
            playbook_code,
            playbook_run,
            inputs or {},
        )

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
        execution_profile: Optional["ExecutionProfile"] = None,  # New parameter
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
        from backend.app.services.playbook_run_executor_admission import (
            prepare_playbook_admission,
        )

        inputs, _admission_snapshot = await prepare_playbook_admission(
            playbook_code=playbook_code,
            profile_id=profile_id,
            workspace_id=workspace_id,
            project_id=project_id,
            inputs=inputs,
        )
        if _admission_snapshot is not None:
            self.playbook_runner.tool_executor.execution_context.update(
                {
                    "workspace_id": workspace_id,
                    "execution_admission_snapshot": (
                        _admission_snapshot.model_dump(mode="json")
                    ),
                }
            )
        playbook_run = await self.playbook_service.load_playbook_run(
            playbook_code=playbook_code,
            locale=locale or "zh-TW",
            workspace_id=workspace_id,
        )

        if not playbook_run:
            raise ValueError(f"Playbook not found: {playbook_code}")

        # If no project_id provided, use workspace.primary_project_id as fallback
        if not project_id and workspace_id:
            try:
                from backend.app.services.mindscape_store import MindscapeStore

                store = MindscapeStore()
                workspace = await store.get_workspace(workspace_id)
                if (
                    workspace
                    and hasattr(workspace, "primary_project_id")
                    and workspace.primary_project_id
                ):
                    project_id = workspace.primary_project_id
                    logger.info(
                        f"PlaybookRunExecutor: Using workspace.primary_project_id={project_id} for playbook {playbook_code}"
                    )
            except Exception as e:
                logger.warning(
                    f"PlaybookRunExecutor: Failed to get workspace.primary_project_id: {e}"
                )

        # Normalize inputs and inject execution context fields for placeholder rendering and tool parameter injection.
        # Enables resolving {{input.workspace_id}}, {{input.project_id}}, {{input.profile_id}}.
        normalized_inputs = inputs.copy() if inputs else {}
        if workspace_id and "workspace_id" not in normalized_inputs:
            normalized_inputs["workspace_id"] = workspace_id
        if project_id and "project_id" not in normalized_inputs:
            normalized_inputs["project_id"] = project_id
        if profile_id and "profile_id" not in normalized_inputs:
            normalized_inputs["profile_id"] = profile_id
        normalized_inputs = self._apply_playbook_input_contract(
            playbook_code, playbook_run, normalized_inputs
        )
        logger.info(
            f"PlaybookRunExecutor: normalized_inputs keys={list(normalized_inputs.keys())}"
        )

        if not context or context.mode != InvocationMode.SUBROUTINE:
            remote_result = await self._maybe_dispatch_remote_execution(
                playbook_code=playbook_code,
                profile_id=profile_id,
                normalized_inputs=normalized_inputs,
                workspace_id=workspace_id,
                project_id=project_id,
            )
            if remote_result is not None:
                return remote_result

        execution_mode = playbook_run.get_execution_mode()
        logger.info(
            f"PlaybookRunExecutor: playbook_code={playbook_code}, execution_mode={execution_mode}, has_json={playbook_run.has_json()}, context_mode={context.mode if context else None}, project_id={project_id}"
        )

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
                    context=context,
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
                    context=context,
                )

        if execution_mode == "workflow" and playbook_run.playbook_json:
            logger.info(
                "PlaybookRunExecutor: Executing %s using Runtime system (playbook.json found)",
                playbook_code,
            )
            return await executor_execute_runtime_workflow(
                executor=self,
                playbook_run=playbook_run,
                playbook_code=playbook_code,
                profile_id=profile_id,
                normalized_inputs=normalized_inputs,
                workspace_id=workspace_id,
                project_id=project_id,
                runtime_result_has_errors_fn=_runtime_result_has_errors,
                is_runner_process_fn=_is_runner_process,
            )

        else:
            logger.info(
                f"Executing {playbook_code} using PlaybookRunner (LLM conversation mode), workspace_id={workspace_id}, project_id={project_id}"
            )

            result = await self.playbook_runner.start_playbook_execution(
                playbook_code=playbook_code,
                profile_id=profile_id,
                inputs=normalized_inputs,
                workspace_id=workspace_id,
                project_id=project_id,
                target_language=target_language,
                variant_id=variant_id,
            )

            return {
                "execution_mode": "conversation",
                "playbook_code": playbook_code,
                "result": result,
                "has_json": False,
            }

    async def _maybe_dispatch_remote_execution(
        self,
        *,
        playbook_code: str,
        profile_id: str,
        normalized_inputs: Dict[str, Any],
        workspace_id: Optional[str],
        project_id: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        return await executor_maybe_dispatch_remote_execution(
            playbook_code=playbook_code,
            profile_id=profile_id,
            normalized_inputs=normalized_inputs,
            workspace_id=workspace_id,
            project_id=project_id,
            execution_dispatch_helpers_fn=self._get_execution_dispatch_helpers,
        )

    def _get_execution_dispatch_helpers(self):
        from backend.app.routes.core.execution_dispatch import (
            dispatch_remote_execution,
            release_backend,
            resolve_and_acquire_backend,
        )

        return (
            dispatch_remote_execution,
            resolve_and_acquire_backend,
            release_backend,
        )

    async def get_playbook_run(
        self, playbook_code: str, locale: Optional[str] = None
    ) -> Optional[PlaybookRun]:
        """
        Get playbook.run definition without executing

        Args:
            playbook_code: Playbook code
            locale: Preferred locale

        Returns:
            PlaybookRun or None if not found
        """
        return await self.playbook_service.load_playbook_run(
            playbook_code=playbook_code, locale=locale or "zh-TW", workspace_id=None
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
        context: PlaybookInvocationContext,
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

        if execution_mode == "workflow" and playbook_run.playbook_json:
            return await self._execute_workflow_legacy(
                playbook_run=playbook_run,
                playbook_code=playbook_code,
                profile_id=profile_id,
                inputs=inputs,
                workspace_id=workspace_id,
                project_id=project_id,
            )
        return await executor_execute_conversation_invocation(
            playbook_code=playbook_code,
            profile_id=profile_id,
            inputs=inputs,
            workspace_id=workspace_id,
            project_id=project_id,
            target_language=target_language,
            variant_id=variant_id,
            invocation_mode="standalone",
            context=context,
            start_playbook_execution_fn=self.playbook_runner.start_playbook_execution,
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
        context: PlaybookInvocationContext,
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

        inputs = executor_merge_plan_node_inputs(
            playbook_code=playbook_code,
            inputs=inputs,
            context=context,
        )

        if context.strategy.wait_for_upstream_tasks and context.plan_context:
            dependencies = context.plan_context.dependencies
            if dependencies:
                logger.info(
                    f"PlaybookRunExecutor: Waiting for upstream tasks: {dependencies}"
                )
                # Upstream task waiting logic to be implemented

        execution_mode = playbook_run.get_execution_mode()

        if execution_mode == "workflow" and playbook_run.playbook_json:
            return await self._execute_workflow_legacy(
                playbook_run=playbook_run,
                playbook_code=playbook_code,
                profile_id=profile_id,
                inputs=inputs,
                workspace_id=workspace_id,
                project_id=project_id,
            )
        return await executor_execute_conversation_invocation(
            playbook_code=playbook_code,
            profile_id=profile_id,
            inputs=inputs,
            workspace_id=workspace_id,
            project_id=project_id,
            target_language=target_language,
            variant_id=variant_id,
            invocation_mode="plan_node",
            context=context,
            start_playbook_execution_fn=self.playbook_runner.start_playbook_execution,
        )

    async def _execute_workflow_legacy(
        self,
        playbook_run: PlaybookRun,
        playbook_code: str,
        profile_id: str,
        inputs: Optional[Dict[str, Any]],
        workspace_id: Optional[str],
        project_id: Optional[str],
    ) -> Dict[str, Any]:
        """Legacy workflow execution (extracted for reuse)."""
        return await executor_execute_legacy_workflow(
            executor=self,
            playbook_run=playbook_run,
            playbook_code=playbook_code,
            profile_id=profile_id,
            inputs=inputs,
            workspace_id=workspace_id,
            project_id=project_id,
            workflow_result_has_errors_fn=_workflow_result_has_errors,
            is_runner_process_fn=_is_runner_process,
        )

    def _load_runtime_providers(self):
        """
        Dynamically load runtime providers from capability packs

        Scans installed capability packs for runtime providers (type: system_runtime)
        and registers them with the RuntimeFactory.
        """
        executor_load_runtime_providers(self.runtime_factory)
