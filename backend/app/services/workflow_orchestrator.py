"""
Workflow Orchestrator

Executes multi-step workflows based on HandoffPlan and playbook.json.
Manages step dependencies, template resolution, and tool execution.
"""

import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional, Set
from collections import defaultdict

from backend.app.models.playbook import (
    HandoffPlan,
    WorkflowStep,
    PlaybookJson,
    PlaybookKind,
    RetryPolicy,
)
from backend.app.services.workflow_template_engine import TemplateEngine
from backend.app.shared.tool_executor import ToolExecutor
from backend.app.services.workflow_step_loop import WorkflowStepLoop
from backend.app.services.playbook_loaders import PlaybookJsonLoader
from backend.app.services.execution_core.clock import utc_now as _utc_now
from backend.app.services.execution_core.errors import RecoverableStepError
from backend.app.services.workflow.remote_route import (
    ensure_remote_tool_child_shell as workflow_ensure_remote_tool_child_shell,
    get_cloud_connector as workflow_get_cloud_connector,
    maybe_execute_tool_via_remote_route as workflow_maybe_execute_tool_via_remote_route,
    resolve_remote_tool_route as workflow_resolve_remote_tool_route,
    resolve_tool_model_override as workflow_resolve_tool_model_override,
)
from backend.app.services.workflow.playbook_runtime import (
    apply_execution_profile_model_override as workflow_apply_execution_profile_model_override,
    ensure_execution_sandbox as workflow_ensure_execution_sandbox,
    resolve_resume_checkpoint as workflow_resolve_resume_checkpoint,
    restore_checkpoint_state as workflow_restore_checkpoint_state,
)
from backend.app.services.workflow.playbook_finalization import (
    finalize_playbook_execution as workflow_finalize_playbook_execution,
)
from backend.app.services.workflow.retry_policy import (
    calculate_retry_delay as workflow_calculate_retry_delay,
    classify_error as workflow_classify_error,
    default_retry_policy as workflow_default_retry_policy,
)
from backend.app.services.workflow.retry_execution import (
    execute_step_with_retry as workflow_execute_step_with_retry,
)
from backend.app.services.workflow.result_mapper import (
    collect_final_outputs as workflow_collect_final_outputs,
    create_step_event as workflow_create_step_event,
    map_tool_result_to_step_outputs as workflow_map_tool_result_to_step_outputs,
)
from backend.app.services.workflow.scheduling import (
    apply_step_result_to_context as workflow_apply_step_result_to_context,
    build_dependency_graph as workflow_build_dependency_graph,
    build_paused_workflow_result as workflow_build_paused_workflow_result,
    build_previous_results as workflow_build_previous_results,
    evaluate_condition as workflow_evaluate_condition,
    get_nested_value as workflow_get_nested_value,
    get_ready_steps as workflow_get_ready_steps,
    get_ready_steps_for_parallel as workflow_get_ready_steps_for_parallel,
    has_output as workflow_has_output,
    normalize_parallel_step_result as workflow_normalize_parallel_step_result,
    should_stop_workflow_after_error as workflow_should_stop_workflow_after_error,
)
from backend.app.services.workflow.step_lifecycle import (
    build_gate_pause_result as workflow_build_gate_pause_result,
    maybe_invoke_step_hook as workflow_maybe_invoke_step_hook,
    resolve_gate_action as workflow_resolve_gate_action,
)
from backend.app.services.workflow.step_runner import (
    execute_workflow_step as workflow_execute_workflow_step,
)
from backend.app.services.workflow.step_dispatch import (
    execute_playbook_slot as workflow_execute_playbook_slot,
    resolve_tool_slot_to_tool_id as workflow_resolve_tool_slot_to_tool_id,
)
from backend.app.services.workflow.tool_execution import (
    execute_tool_step as workflow_execute_tool_step,
)

logger = logging.getLogger(__name__)


class WorkflowOrchestrator:
    """Orchestrates multi-step workflow execution"""

    def __init__(self, store=None):
        self.tool_executor = ToolExecutor()
        self.template_engine = TemplateEngine()
        self.step_loop = WorkflowStepLoop(
            self.template_engine, self.tool_executor, store
        )
        self.store = store

    def _get_cloud_connector(self):
        return workflow_get_cloud_connector()

    def _ensure_remote_tool_child_shell(self, **kwargs):
        return workflow_ensure_remote_tool_child_shell(**kwargs)

    def _resolve_remote_tool_route(
        self,
        playbook_inputs: Optional[Dict[str, Any]],
        *,
        step_id: str,
        tool_id: str,
    ) -> Optional[Dict[str, Any]]:
        return workflow_resolve_remote_tool_route(
            playbook_inputs,
            step_id=step_id,
            tool_id=tool_id,
        )

    def _resolve_tool_model_override(
        self,
        *,
        tool_id: str,
        playbook_inputs: Optional[Dict[str, Any]],
        remote_route: Optional[Dict[str, Any]] = None,
        execution_profile: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        return workflow_resolve_tool_model_override(
            tool_id=tool_id,
            playbook_inputs=playbook_inputs,
            remote_route=remote_route,
            execution_profile=execution_profile,
        )

    async def _maybe_execute_tool_via_remote_route(
        self,
        *,
        step_id: str,
        tool_id: str,
        tool_inputs: Dict[str, Any],
        playbook_inputs: Dict[str, Any],
        execution_id: Optional[str],
        workspace_id: Optional[str],
    ) -> tuple[bool, Any]:
        return await workflow_maybe_execute_tool_via_remote_route(
            step_id=step_id,
            tool_id=tool_id,
            tool_inputs=tool_inputs,
            playbook_inputs=playbook_inputs,
            execution_id=execution_id,
            workspace_id=workspace_id,
            get_cloud_connector_fn=self._get_cloud_connector,
            ensure_remote_tool_child_shell_fn=self._ensure_remote_tool_child_shell,
        )

    async def _resolve_tool_slot_to_tool_id(
        self,
        *,
        step: Any,
        workspace_id: Optional[str],
        project_id: Optional[str],
    ) -> str:
        return await workflow_resolve_tool_slot_to_tool_id(
            step=step,
            store=self.store,
            workspace_id=workspace_id,
            project_id=project_id,
        )

    async def _execute_playbook_slot(
        self,
        *,
        step: Any,
        resolved_inputs: Dict[str, Any],
        execution_id: Optional[str],
        workspace_id: Optional[str],
        profile_id: Optional[str],
        project_id: Optional[str],
    ) -> Dict[str, Any]:
        previous_depth = getattr(self, "_playbook_slot_depth", 0)
        self._playbook_slot_depth = previous_depth + 1
        try:
            return await workflow_execute_playbook_slot(
                step=step,
                current_depth=previous_depth,
                resolved_inputs=resolved_inputs,
                execution_id=execution_id,
                workspace_id=workspace_id,
                profile_id=profile_id,
                project_id=project_id,
                load_playbook_json_fn=self.load_playbook_json,
                execute_playbook_steps_fn=self._execute_playbook_steps,
            )
        finally:
            self._playbook_slot_depth = previous_depth

    async def _execute_tool_step(
        self,
        *,
        step: Any,
        tool_id: str,
        resolved_inputs: Dict[str, Any],
        playbook_inputs: Dict[str, Any],
        playbook_json: Any,
        execution_id: Optional[str],
        workspace_id: Optional[str],
        profile_id: Optional[str],
    ) -> Any:
        return await workflow_execute_tool_step(
            step=step,
            tool_id=tool_id,
            resolved_inputs=resolved_inputs,
            playbook_inputs=playbook_inputs,
            execution_profile=getattr(playbook_json, "execution_profile", None),
            execution_id=execution_id,
            workspace_id=workspace_id,
            profile_id=profile_id,
            resolve_remote_tool_route_fn=self._resolve_remote_tool_route,
            resolve_tool_model_override_fn=self._resolve_tool_model_override,
            maybe_execute_tool_via_remote_route_fn=self._maybe_execute_tool_via_remote_route,
            execute_tool_fn=self.tool_executor.execute_tool,
        )

    def _resolve_resume_checkpoint(
        self,
        *,
        playbook_inputs: Dict[str, Any],
        execution_id: Optional[str],
        playbook_json: Any,
    ) -> Optional[Dict[str, Any]]:
        return workflow_resolve_resume_checkpoint(
            playbook_inputs=playbook_inputs,
            execution_id=execution_id,
            playbook_code=getattr(playbook_json, "playbook_code", None),
        )

    def _restore_checkpoint_state(
        self,
        *,
        playbook_inputs: Dict[str, Any],
        resume_checkpoint: Optional[Dict[str, Any]],
    ) -> tuple[Dict[str, Dict[str, Any]], Set[str]]:
        return workflow_restore_checkpoint_state(
            playbook_inputs=playbook_inputs,
            resume_checkpoint=resume_checkpoint,
        )

    def _apply_execution_profile_model_override(
        self,
        *,
        playbook_json: Any,
        playbook_inputs: Dict[str, Any],
    ) -> Optional[str]:
        return workflow_apply_execution_profile_model_override(
            playbook_json=playbook_json,
            playbook_inputs=playbook_inputs,
        )

    async def _ensure_execution_sandbox(
        self,
        *,
        playbook_json: Any,
        execution_id: Optional[str],
        workspace_id: Optional[str],
        project_id: Optional[str],
        resume_checkpoint: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        return await workflow_ensure_execution_sandbox(
            store=self.store,
            playbook_json=playbook_json,
            execution_id=execution_id,
            workspace_id=workspace_id,
            project_id=project_id,
            resume_checkpoint=resume_checkpoint,
        )

    async def _finalize_playbook_execution(
        self,
        *,
        playbook_json: Any,
        playbook_inputs: Dict[str, Any],
        step_outputs: Dict[str, Dict[str, Any]],
        final_outputs: Dict[str, Any],
        execution_id: Optional[str],
        workspace_id: Optional[str],
        sandbox_id: Optional[str],
    ) -> Dict[str, Any]:
        return await workflow_finalize_playbook_execution(
            store=self.store,
            playbook_json=playbook_json,
            playbook_inputs=playbook_inputs,
            step_outputs=step_outputs,
            final_outputs=final_outputs,
            execution_id=execution_id,
            workspace_id=workspace_id,
            sandbox_id=sandbox_id,
        )

    def load_playbook_json(self, playbook_code: str) -> Optional[PlaybookJson]:
        """
        Load playbook.json file using PlaybookJsonLoader

        Args:
            playbook_code: Playbook code

        Returns:
            PlaybookJson model or None if not found
        """
        return PlaybookJsonLoader.load_playbook_json(playbook_code)

    async def execute_workflow(
        self,
        handoff_plan: HandoffPlan,
        execution_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute workflow from HandoffPlan with parallel execution support

        Args:
            handoff_plan: HandoffPlan with workflow steps

        Returns:
            Dict with execution results for each step
        """
        results = {}
        workflow_context = handoff_plan.context.copy()
        # playbook_inputs are stored in workflow_context
        playbook_inputs = workflow_context.copy()

        dependency_graph = self._build_dependency_graph(handoff_plan.steps)
        completed_steps: Set[str] = set()
        pending_steps = {step.playbook_code: step for step in handoff_plan.steps}

        while pending_steps:
            ready_steps = self._get_ready_steps_for_parallel(
                pending_steps,
                completed_steps,
                dependency_graph,
                results,
                playbook_inputs,
            )

            if not ready_steps:
                remaining = list(pending_steps.keys())
                logger.error(
                    f"No ready steps found. Remaining: {remaining}, Completed: {completed_steps}"
                )
                break

            logger.info(
                f"Executing {len(ready_steps)} steps in parallel: {[s.playbook_code for s in ready_steps]}"
            )

            previous_results = workflow_build_previous_results(results)

            step_tasks = [
                self._execute_step_with_retry(
                    step,
                    workflow_context,
                    previous_results,
                    execution_id=execution_id,
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    project_id=project_id,
                    step_index=len(completed_steps),
                )
                for step in ready_steps
            ]

            step_results = await asyncio.gather(*step_tasks, return_exceptions=True)

            for step, step_result in zip(ready_steps, step_results):
                step_result = workflow_normalize_parallel_step_result(
                    step_playbook_code=step.playbook_code,
                    step_result=step_result,
                )
                results[step.playbook_code] = step_result
                completed_steps.add(step.playbook_code)
                del pending_steps[step.playbook_code]

                if (
                    isinstance(step_result, dict)
                    and step_result.get("status") == "paused"
                ):
                    # Stop the workflow immediately. Caller can resume using checkpoint.
                    return workflow_build_paused_workflow_result(
                        step_playbook_code=step.playbook_code,
                        results=results,
                        workflow_context=workflow_context,
                        step_result=step_result,
                    )

                workflow_apply_step_result_to_context(
                    workflow_context=workflow_context,
                    step_result=step_result,
                )

                if workflow_should_stop_workflow_after_error(
                    step=step,
                    step_result=step_result,
                ):
                    pending_steps.clear()
                    break

        logger.info(
            f"WorkflowOrchestrator.execute_workflow: returning results with {len(results)} steps"
        )
        logger.info(
            f"WorkflowOrchestrator.execute_workflow: results keys: {list(results.keys())}"
        )
        return {"status": "completed", "steps": results, "context": workflow_context}

    def _build_dependency_graph(self, steps: List[WorkflowStep]) -> Dict[str, Set[str]]:
        return workflow_build_dependency_graph(steps)

    def _get_ready_steps_for_parallel(
        self,
        pending_steps: Dict[str, WorkflowStep],
        completed_steps: Set[str],
        dependency_graph: Dict[str, Set[str]],
        results: Dict[str, Dict[str, Any]],
        playbook_inputs: Optional[Dict[str, Any]] = None,
    ) -> List[WorkflowStep]:
        return workflow_get_ready_steps_for_parallel(
            pending_steps=pending_steps,
            completed_steps=completed_steps,
            dependency_graph=dependency_graph,
            results=results,
            playbook_inputs=playbook_inputs,
        )

    def _evaluate_condition(
        self,
        step: WorkflowStep,
        results: Dict[str, Dict[str, Any]],
        playbook_inputs: Optional[Dict[str, Any]] = None,
        step_outputs: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> bool:
        return workflow_evaluate_condition(
            step=step,
            results=results,
            playbook_inputs=playbook_inputs,
            step_outputs=step_outputs,
        )

    def _get_nested_value(self, obj: Dict[str, Any], path: str) -> Any:
        return workflow_get_nested_value(obj, path)

    def _has_output(
        self, results: Dict[str, Dict[str, Any]], playbook_code: str, output_key: str
    ) -> bool:
        return workflow_has_output(results, playbook_code, output_key)

    async def execute_workflow_step(
        self,
        step: WorkflowStep,
        workflow_context: Dict[str, Any],
        previous_results: Dict[str, Dict[str, Any]],
        execution_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        project_id: Optional[str] = None,
        step_index: int = 0,
    ) -> Dict[str, Any]:
        """
        Execute a single workflow step

        Args:
            step: WorkflowStep to execute
            workflow_context: Current workflow context
            previous_results: Results from previous steps

        Returns:
            Step execution result with outputs
        """
        return await workflow_execute_workflow_step(
            step=step,
            workflow_context=workflow_context,
            previous_results=previous_results,
            execution_id=execution_id,
            workspace_id=workspace_id,
            profile_id=profile_id,
            project_id=project_id,
            load_playbook_json_fn=self.load_playbook_json,
            prepare_workflow_step_inputs_fn=self.template_engine.prepare_workflow_step_inputs,
            execute_playbook_steps_fn=self._execute_playbook_steps,
        )

    async def _execute_playbook_steps(
        self,
        playbook_json: PlaybookJson,
        playbook_inputs: Dict[str, Any],
        execution_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute all steps in playbook.json

        Args:
            playbook_json: PlaybookJson definition
            playbook_inputs: Resolved playbook inputs
            execution_id: Execution ID
            workspace_id: Workspace ID
            profile_id: Profile ID
            project_id: Project ID for sandbox context

        Returns:
            Dict with step outputs and final playbook outputs
        """
        # Best-effort resume support:
        # - If _workflow_checkpoint is provided in inputs, reuse sandbox + step_outputs.
        # - Gate decisions are passed via inputs.gate_decisions[step_id].action = "approved"|"rejected".
        resume_checkpoint = self._resolve_resume_checkpoint(
            playbook_inputs=playbook_inputs,
            execution_id=execution_id,
            playbook_json=playbook_json,
        )
        logger.info(
            f"WorkflowOrchestrator._execute_playbook_steps: Starting execution. project_id={project_id}, workspace_id={workspace_id}, playbook_inputs keys: {list(playbook_inputs.keys())}"
        )
        sandbox_id = await self._ensure_execution_sandbox(
            playbook_json=playbook_json,
            execution_id=execution_id,
            workspace_id=workspace_id,
            project_id=project_id,
            resume_checkpoint=resume_checkpoint,
        )

        step_outputs, completed_steps = self._restore_checkpoint_state(
            playbook_inputs=playbook_inputs,
            resume_checkpoint=resume_checkpoint,
        )

        self._apply_execution_profile_model_override(
            playbook_json=playbook_json,
            playbook_inputs=playbook_inputs,
        )

        while len(completed_steps) < len(playbook_json.steps):
            ready_steps = self._get_ready_steps(
                playbook_json.steps, completed_steps, playbook_inputs, step_outputs
            )
            logger.debug(
                f"WorkflowOrchestrator._execute_playbook_steps: Found {len(ready_steps)} ready steps, playbook_inputs keys: {list(playbook_inputs.keys())}"
            )

            if not ready_steps:
                raise RuntimeError(
                    "Circular dependency or missing dependencies detected"
                )

            for step in ready_steps:
                try:
                    step_index = len(completed_steps)
                    # Log playbook_inputs for debugging
                    logger.debug(
                        f"WorkflowOrchestrator._execute_playbook_steps: Executing step {step.id}, playbook_inputs keys: {list(playbook_inputs.keys())}"
                    )

                    # P3-4c: pre_step hook (failure prevents step execution)
                    await workflow_maybe_invoke_step_hook(
                        step_id=step.id,
                        hook_phase="pre_step",
                        hook_spec_model=(
                            step.hooks.pre_step
                            if hasattr(step, "hooks") and step.hooks
                            else None
                        ),
                        playbook_inputs=playbook_inputs,
                        execution_id=execution_id,
                        workspace_id=workspace_id,
                        profile_id=profile_id,
                        step_outputs=step_outputs,
                        strict=True,
                    )

                    step_result = await self._execute_single_step(
                        step,
                        playbook_json,
                        playbook_inputs,
                        step_outputs,
                        playbook_json.inputs,
                        execution_id=execution_id,
                        workspace_id=workspace_id,
                        profile_id=profile_id,
                        project_id=project_id,
                        step_index=step_index,
                    )
                    step_outputs[step.id] = step_result
                    step_result_keys = (
                        list(step_result.keys())
                        if isinstance(step_result, dict)
                        else "N/A"
                    )
                    step_result_preview = {}
                    if isinstance(step_result, dict):
                        for k, v in step_result.items():
                            if isinstance(v, (list, dict)):
                                step_result_preview[k] = (
                                    f"{type(v).__name__}(len={len(v)})"
                                )
                            else:
                                step_result_preview[k] = (
                                    str(v)[:100] if len(str(v)) > 100 else str(v)
                                )
                    logger.info(
                        f"Step {step.id} completed successfully. Output keys: {step_result_keys}, Preview: {step_result_preview}"
                    )

                    # P3-4c: post_step hook (non-fatal)
                    await workflow_maybe_invoke_step_hook(
                        step_id=step.id,
                        hook_phase="post_step",
                        hook_spec_model=(
                            step.hooks.post_step
                            if hasattr(step, "hooks") and step.hooks
                            else None
                        ),
                        playbook_inputs=playbook_inputs,
                        execution_id=execution_id,
                        workspace_id=workspace_id,
                        profile_id=profile_id,
                        step_outputs=step_outputs,
                    )

                    # Gate pause: stop after completing the step, wait for external approval.
                    gate = getattr(step, "gate", None)
                    if gate and getattr(gate, "required", False):
                        action = workflow_resolve_gate_action(
                            playbook_inputs=playbook_inputs,
                            step_id=step.id,
                        )
                        if action == "rejected":
                            raise RuntimeError(f"Gate rejected for step {step.id}")
                        if action != "approved":
                            partial_outputs = self._collect_final_outputs(
                                playbook_json.outputs, step_outputs
                            )
                            return workflow_build_gate_pause_result(
                                step_id=step.id,
                                gate=gate,
                                execution_id=execution_id,
                                playbook_code=getattr(
                                    playbook_json,
                                    "playbook_code",
                                    None,
                                ),
                                sandbox_id=sandbox_id,
                                completed_steps=completed_steps,
                                step_outputs=step_outputs,
                                partial_outputs=partial_outputs,
                                created_at=_utc_now(),
                            )
                        # Approved: mark the step completed and continue.
                        completed_steps.add(step.id)
                        continue

                    completed_steps.add(step.id)
                except Exception as e:
                    error_msg = str(e)[:500] if len(str(e)) > 500 else str(e)
                    logger.error(f"Step {step.id} failed: {error_msg}")
                    if execution_id and workspace_id and self.store:
                        self._create_step_event(
                            execution_id=execution_id,
                            workspace_id=workspace_id,
                            profile_id=profile_id,
                            step_id=step.id,
                            step_name=step.id,
                            step_index=len(completed_steps),
                            status="failed",
                            error=str(e),
                        )

                    # P3-4c: on_error hook (non-fatal)
                    await workflow_maybe_invoke_step_hook(
                        step_id=step.id,
                        hook_phase="on_error",
                        hook_spec_model=(
                            step.hooks.on_error
                            if hasattr(step, "hooks") and step.hooks
                            else None
                        ),
                        playbook_inputs=playbook_inputs,
                        execution_id=execution_id,
                        workspace_id=workspace_id,
                        profile_id=profile_id,
                        step_outputs=step_outputs,
                        error=error_msg,
                    )

                    raise

        final_outputs = self._collect_final_outputs(playbook_json.outputs, step_outputs)
        return await self._finalize_playbook_execution(
            playbook_json=playbook_json,
            playbook_inputs=playbook_inputs,
            step_outputs=step_outputs,
            final_outputs=final_outputs,
            execution_id=execution_id,
            workspace_id=workspace_id,
            sandbox_id=sandbox_id,
        )

    def _get_ready_steps(
        self,
        steps: List[Any],
        completed_steps: set,
        playbook_inputs: Optional[Dict[str, Any]] = None,
        step_outputs: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> List[Any]:
        return workflow_get_ready_steps(
            steps=steps,
            completed_steps=completed_steps,
            playbook_inputs=playbook_inputs,
            step_outputs=step_outputs,
        )

    async def _execute_single_step_iteration(
        self,
        step: Any,
        playbook_json: Any,
        playbook_inputs: Dict[str, Any],
        step_outputs: Dict[str, Dict[str, Any]],
        playbook_input_defs: Dict[str, Any],
        execution_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        project_id: Optional[str] = None,
        step_index: int = 0,
    ) -> Dict[str, Any]:
        """Execute a single step iteration (used by loop handler)"""
        # Mark step as in loop iteration to prevent recursion
        step._in_loop_iteration = True
        try:
            return await self._execute_single_step(
                step,
                playbook_json,
                playbook_inputs,
                step_outputs,
                playbook_input_defs,
                execution_id=execution_id,
                workspace_id=workspace_id,
                profile_id=profile_id,
                project_id=project_id,
                step_index=step_index,
            )
        finally:
            # Clean up the flag
            if hasattr(step, "_in_loop_iteration"):
                delattr(step, "_in_loop_iteration")

    async def _execute_single_step(
        self,
        step: Any,
        playbook_json: Any,
        playbook_inputs: Dict[str, Any],
        step_outputs: Dict[str, Dict[str, Any]],
        playbook_input_defs: Dict[str, Any],
        execution_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        project_id: Optional[str] = None,
        step_index: int = 0,
    ) -> Dict[str, Any]:
        """
        Execute a single playbook step

        Args:
            step: PlaybookStep to execute
            playbook_inputs: Playbook input values
            step_outputs: Completed step outputs
            playbook_input_defs: Playbook input definitions

        Returns:
            Step output dict
        """
        step_started_at = _utc_now()

        if execution_id and workspace_id and self.store:
            self._create_step_event(
                execution_id=execution_id,
                workspace_id=workspace_id,
                profile_id=profile_id,
                step_id=step.id,
                step_name=step.id,
                step_index=step_index,
                status="running",
                started_at=step_started_at,
            )

        try:
            # Check if step has for_each (loop support)
            # Only handle for_each at the top level, not in iterations
            if (
                hasattr(step, "for_each")
                and step.for_each
                and not hasattr(step, "_in_loop_iteration")
            ):
                # Execute step for each item in the array using loop handler
                return await self.step_loop.execute_step_with_loop(
                    step,
                    self._execute_single_step_iteration,
                    playbook_json,
                    playbook_inputs,
                    step_outputs,
                    playbook_input_defs,
                    execution_id=execution_id,
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    project_id=project_id,
                    step_index=step_index,
                )

            # Add workspace_id to playbook_inputs for template resolution
            # This allows {{workspace_id}} template variable to be resolved
            playbook_inputs_with_context = playbook_inputs.copy()
            if workspace_id:
                playbook_inputs_with_context["workspace_id"] = workspace_id
            if execution_id:
                playbook_inputs_with_context["execution_id"] = execution_id

            workflow_context: Dict[str, Any] = {}
            if workspace_id:
                workflow_context["workspace_id"] = workspace_id
            if execution_id:
                workflow_context["execution_id"] = execution_id
            if profile_id:
                workflow_context["profile_id"] = profile_id

            resolved_inputs = self.template_engine.prepare_playbook_inputs(
                step, playbook_inputs_with_context, step_outputs, workflow_context
            )

            # Resolve tool: use tool_slot field (tool field is deprecated and removed)
            tool_id = None
            if hasattr(step, "tool_slot") and step.tool_slot:
                tool_id = await self._resolve_tool_slot_to_tool_id(
                    step=step,
                    workspace_id=workspace_id,
                    project_id=project_id,
                )
            elif hasattr(step, "playbook_slot") and step.playbook_slot:
                return await self._execute_playbook_slot(
                    step=step,
                    resolved_inputs=resolved_inputs,
                    execution_id=execution_id,
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    project_id=project_id,
                )

            else:
                raise ValueError(
                    "PlaybookStep must have 'tool', 'tool_slot', or 'playbook_slot'"
                )

            tool_result = await self._execute_tool_step(
                step=step,
                tool_id=tool_id,
                resolved_inputs=resolved_inputs,
                playbook_inputs=playbook_inputs,
                playbook_json=playbook_json,
                execution_id=execution_id,
                workspace_id=workspace_id,
                profile_id=profile_id,
            )

            step_output = workflow_map_tool_result_to_step_outputs(
                step_id=step.id,
                output_defs=step.outputs,
                tool_result=tool_result,
            )

            step_completed_at = _utc_now()

            if execution_id and workspace_id and self.store:
                self._create_step_event(
                    execution_id=execution_id,
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    step_id=step.id,
                    step_name=step.id,
                    step_index=step_index,
                    status="completed",
                    started_at=step_started_at,
                    completed_at=step_completed_at,
                )

            return step_output
        except Exception as e:
            step_completed_at = _utc_now()
            if execution_id and workspace_id and self.store:
                self._create_step_event(
                    execution_id=execution_id,
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    step_id=step.id,
                    step_name=step.id,
                    step_index=step_index,
                    status="failed",
                    started_at=step_started_at,
                    completed_at=step_completed_at,
                    error=str(e),
                )
            raise

    def _collect_final_outputs(
        self, output_defs: Dict[str, Any], step_outputs: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        return workflow_collect_final_outputs(output_defs, step_outputs)

    def _create_step_event(
        self,
        execution_id: str,
        workspace_id: str,
        profile_id: Optional[str],
        step_id: str,
        step_name: str,
        step_index: int,
        status: str,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        error: Optional[str] = None,
    ):
        workflow_create_step_event(
            store=self.store,
            execution_id=execution_id,
            workspace_id=workspace_id,
            profile_id=profile_id,
            step_id=step_id,
            step_name=step_name,
            step_index=step_index,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            error=error,
        )

    async def _execute_step_with_retry(
        self,
        step: WorkflowStep,
        workflow_context: Dict[str, Any],
        previous_results: Dict[str, Dict[str, Any]],
        execution_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        project_id: Optional[str] = None,
        step_index: int = 0,
    ) -> Dict[str, Any]:
        """
        Execute workflow step with retry logic

        Args:
            step: WorkflowStep to execute
            workflow_context: Current workflow context
            previous_results: Results from previous steps

        Returns:
            Step execution result with outputs or error
        """
        return await workflow_execute_step_with_retry(
            step=step,
            workflow_context=workflow_context,
            previous_results=previous_results,
            execution_id=execution_id,
            workspace_id=workspace_id,
            profile_id=profile_id,
            project_id=project_id,
            step_index=step_index,
            execute_workflow_step_fn=self.execute_workflow_step,
            get_default_retry_policy_fn=self._get_default_retry_policy,
            calculate_retry_delay_fn=self._calculate_retry_delay,
            classify_error_fn=self._classify_error,
        )

    def _get_default_retry_policy(self, kind: PlaybookKind) -> RetryPolicy:
        return workflow_default_retry_policy(kind)

    def _calculate_retry_delay(self, attempt: int, retry_policy: RetryPolicy) -> float:
        return workflow_calculate_retry_delay(attempt, retry_policy)

    def _classify_error(self, error: str) -> str:
        return workflow_classify_error(error)
