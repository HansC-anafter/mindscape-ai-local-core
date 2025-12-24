"""
Workflow Orchestrator

Executes multi-step workflows based on HandoffPlan and playbook.json.
Manages step dependencies, template resolution, and tool execution.
"""

import json
import logging
import asyncio
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
from collections import defaultdict

from backend.app.models.playbook import (
    HandoffPlan,
    WorkflowStep,
    PlaybookJson,
    PlaybookKind,
    InteractionMode,
    RetryPolicy,
    ErrorHandlingStrategy
)
from backend.app.services.workflow_template_engine import TemplateEngine
from backend.app.shared.tool_executor import ToolExecutor
from backend.app.services.tool_slot_resolver import get_tool_slot_resolver, SlotNotFoundError
from backend.app.services.tool_policy_engine import get_tool_policy_engine, PolicyViolationError
from backend.app.services.workflow_step_loop import WorkflowStepLoop
from backend.app.services.playbook_loaders import PlaybookJsonLoader

logger = logging.getLogger(__name__)


class WorkflowOrchestrator:
    """Orchestrates multi-step workflow execution"""

    def __init__(self, store=None):
        self.tool_executor = ToolExecutor()
        self.template_engine = TemplateEngine()
        self.step_loop = WorkflowStepLoop(self.template_engine, self.tool_executor, store)
        self.store = store

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
        project_id: Optional[str] = None
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

        dependency_graph = self._build_dependency_graph(handoff_plan.steps)
        completed_steps: Set[str] = set()
        pending_steps = {step.playbook_code: step for step in handoff_plan.steps}

        while pending_steps:
            ready_steps = self._get_ready_steps_for_parallel(
                pending_steps,
                completed_steps,
                dependency_graph,
                results
            )

            if not ready_steps:
                remaining = list(pending_steps.keys())
                logger.error(f"No ready steps found. Remaining: {remaining}, Completed: {completed_steps}")
                break

            logger.info(f"Executing {len(ready_steps)} steps in parallel: {[s.playbook_code for s in ready_steps]}")

            previous_results = {}
            for prev_playbook_code, prev_result in results.items():
                if prev_result.get('outputs'):
                    previous_results[prev_playbook_code] = prev_result['outputs']

            step_tasks = [
                self._execute_step_with_retry(
                    step,
                    workflow_context,
                    previous_results,
                    execution_id=execution_id,
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    project_id=project_id,
                    step_index=len(completed_steps)
                )
                for step in ready_steps
            ]

            step_results = await asyncio.gather(*step_tasks, return_exceptions=True)

            for step, step_result in zip(ready_steps, step_results):
                if isinstance(step_result, Exception):
                    logger.error(f"Step {step.playbook_code} raised exception: {step_result}")
                    step_result = {
                        'status': 'error',
                        'error': str(step_result),
                        'error_type': 'exception'
                    }

                logger.info(f"WorkflowOrchestrator: step {step.playbook_code} result keys: {list(step_result.keys()) if isinstance(step_result, dict) else 'not dict'}")
                logger.info(f"WorkflowOrchestrator: step {step.playbook_code} result status: {step_result.get('status') if isinstance(step_result, dict) else 'unknown'}")
                results[step.playbook_code] = step_result
                completed_steps.add(step.playbook_code)
                del pending_steps[step.playbook_code]

                if step_result.get('status') == 'completed' and step_result.get('outputs'):
                    workflow_context.update(step_result['outputs'])

                if step_result.get('status') == 'error':
                    error_handling = step.error_handling
                    if error_handling == ErrorHandlingStrategy.STOP_WORKFLOW:
                        logger.error(f"Step {step.playbook_code} failed, stopping workflow")
                        pending_steps.clear()
                        break
                    elif error_handling == ErrorHandlingStrategy.CONTINUE_ON_ERROR:
                        logger.warning(f"Step {step.playbook_code} failed, continuing workflow")
                    elif error_handling == ErrorHandlingStrategy.SKIP_STEP:
                        logger.warning(f"Step {step.playbook_code} failed, skipping step")
                    elif error_handling in [ErrorHandlingStrategy.RETRY_THEN_STOP, ErrorHandlingStrategy.RETRY_THEN_CONTINUE]:
                        if step_result.get('retries_exhausted'):
                            if error_handling == ErrorHandlingStrategy.RETRY_THEN_STOP:
                                logger.error(f"Step {step.playbook_code} failed after retries, stopping workflow")
                                pending_steps.clear()
                                break
                            else:
                                logger.warning(f"Step {step.playbook_code} failed after retries, continuing workflow")

        logger.info(f"WorkflowOrchestrator.execute_workflow: returning results with {len(results)} steps")
        logger.info(f"WorkflowOrchestrator.execute_workflow: results keys: {list(results.keys())}")
        return {
            'steps': results,
            'context': workflow_context
        }

    def _build_dependency_graph(self, steps: List[WorkflowStep]) -> Dict[str, Set[str]]:
        """
        Build dependency graph for workflow steps

        Args:
            steps: List of workflow steps

        Returns:
            Dict mapping step playbook_code to set of dependencies (playbook_codes it depends on)
        """
        graph = {}
        step_map = {step.playbook_code: step for step in steps}

        for step in steps:
            dependencies = set()

            for input_name, input_value in step.inputs.items():
                if isinstance(input_value, str) and input_value.startswith('$previous.'):
                    parts = input_value.split('.')
                    if len(parts) >= 2:
                        prev_playbook_code = parts[1]
                        if prev_playbook_code in step_map:
                            dependencies.add(prev_playbook_code)

            for mapping in step.input_mapping.values():
                if isinstance(mapping, str) and mapping.startswith('$previous.'):
                    parts = mapping.split('.')
                    if len(parts) >= 2:
                        prev_playbook_code = parts[1]
                        if prev_playbook_code in step_map:
                            dependencies.add(prev_playbook_code)

            graph[step.playbook_code] = dependencies

        return graph

    def _get_ready_steps_for_parallel(
        self,
        pending_steps: Dict[str, WorkflowStep],
        completed_steps: Set[str],
        dependency_graph: Dict[str, Set[str]],
        results: Dict[str, Dict[str, Any]]
    ) -> List[WorkflowStep]:
        """
        Get steps that are ready to execute in parallel

        Args:
            pending_steps: Dict of pending steps by playbook_code
            completed_steps: Set of completed step playbook_codes
            dependency_graph: Dependency graph
            results: Current execution results

        Returns:
            List of ready steps that can be executed in parallel
        """
        ready_steps = []

        for playbook_code, step in pending_steps.items():
            if playbook_code in completed_steps:
                continue

            dependencies = dependency_graph.get(playbook_code, set())

            if not dependencies:
                if self._evaluate_condition(step, results):
                    ready_steps.append(step)
                continue

            all_dependencies_met = True
            for dep in dependencies:
                if dep not in completed_steps:
                    all_dependencies_met = False
                    break
                dep_result = results.get(dep, {})
                if dep_result.get('status') != 'completed':
                    all_dependencies_met = False
                    break

            if all_dependencies_met:
                if self._evaluate_condition(step, results):
                    ready_steps.append(step)
                else:
                    logger.info(f"Step {playbook_code} condition not met, skipping")
                    completed_steps.add(playbook_code)
                    results[playbook_code] = {
                        'status': 'skipped',
                        'reason': 'condition_not_met'
                    }
                    del pending_steps[playbook_code]

        return ready_steps

    def _evaluate_condition(
        self,
        step: WorkflowStep,
        results: Dict[str, Dict[str, Any]],
        playbook_inputs: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Evaluate condition for workflow step

        Args:
            step: WorkflowStep with optional condition
            results: Current execution results
            playbook_inputs: Playbook inputs for template evaluation

        Returns:
            True if step should execute, False if should skip
        """
        if not step.condition:
            return True

        try:
            condition = step.condition.strip()

            # Handle Jinja2 template syntax: {{input.xxx or input.yyy}}
            if condition.startswith('{{') and condition.endswith('}}'):
                # Extract expression from {{...}}
                expr = condition[2:-2].strip()

                # Direct evaluation: input.xxx or input.yyy -> playbook_inputs.get('xxx') or playbook_inputs.get('yyy')
                input_dict = playbook_inputs or {}
                try:
                    # Replace input.xxx with input_dict.get('xxx')
                    import re
                    python_expr = expr
                    # Replace all input.xxx patterns with input_dict.get('xxx')
                    python_expr = re.sub(r'input\.(\w+)', r"input_dict.get('\1')", python_expr)
                    result_value = eval(python_expr, {'__builtins__': {}, 'input_dict': input_dict})
                    logger.debug(f"Condition '{condition}' (expr: '{expr}') evaluated to: {result_value} (bool: {bool(result_value)})")
                    return bool(result_value)
                except Exception as e:
                    logger.warning(f"Failed to evaluate condition '{condition}' for step {step.playbook_code}: {e}")
                    return True

            if condition.startswith('$previous.'):
                parts = condition.split('.')
                if len(parts) >= 3:
                    prev_playbook_code = parts[1]
                    field_path = '.'.join(parts[2:])

                    prev_result = results.get(prev_playbook_code, {})
                    if prev_result.get('status') != 'completed':
                        return False

                    value = self._get_nested_value(prev_result, field_path)
                    return bool(value)

            elif condition.startswith('$context.'):
                field_path = condition.replace('$context.', '')
                value = self._get_nested_value(results, field_path)
                return bool(value)

            else:
                return eval(condition, {
                    '__builtins__': {},
                    'results': results,
                    'previous': lambda code: results.get(code, {}),
                    'has_output': lambda code, key: self._has_output(results, code, key)
                })

        except Exception as e:
            logger.warning(f"Failed to evaluate condition '{step.condition}' for step {step.playbook_code}: {e}")
            return True

    def _get_nested_value(self, obj: Dict[str, Any], path: str) -> Any:
        """Get nested value from dict using dot notation"""
        parts = path.split('.')
        value = obj
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return None
            if value is None:
                return None
        return value

    def _has_output(self, results: Dict[str, Dict[str, Any]], playbook_code: str, output_key: str) -> bool:
        """Check if a playbook has a specific output"""
        result = results.get(playbook_code, {})
        outputs = result.get('outputs', {})
        return output_key in outputs

    async def execute_workflow_step(
        self,
        step: WorkflowStep,
        workflow_context: Dict[str, Any],
        previous_results: Dict[str, Dict[str, Any]],
        execution_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        project_id: Optional[str] = None,
        step_index: int = 0
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
        playbook_json = self.load_playbook_json(step.playbook_code)
        if not playbook_json:
            raise ValueError(f"playbook.json not found for {step.playbook_code}")

        resolved_inputs = self.template_engine.prepare_workflow_step_inputs(
            step,
            previous_results,
            workflow_context
        )

        # Merge workflow_context into resolved_inputs to ensure inputs are available for template resolution
        # This is critical for playbook.json steps that use {{input.xxx}} templates
        # The workflow_context contains the original inputs passed to the playbook execution
        if workflow_context:
            # Merge workflow_context into resolved_inputs, but don't overwrite existing keys
            for key, value in workflow_context.items():
                if key not in resolved_inputs:
                    resolved_inputs[key] = value
            logger.info(f"WorkflowOrchestrator.execute_workflow_step: Merged workflow_context into resolved_inputs for {step.playbook_code}. Keys: {list(resolved_inputs.keys())}")

        if step.kind == PlaybookKind.SYSTEM_TOOL:
            if InteractionMode.SILENT in step.interaction_mode:
                return await self._execute_silently(playbook_json, resolved_inputs, execution_id, workspace_id, profile_id, project_id)
            else:
                return await self._execute_with_minimal_ui(playbook_json, resolved_inputs, execution_id, workspace_id, profile_id, project_id)

        elif step.kind == PlaybookKind.USER_WORKFLOW:
            if InteractionMode.NEEDS_REVIEW in step.interaction_mode:
                logger.info(f"Step {step.playbook_code} requires review")
            if InteractionMode.CONVERSATIONAL in step.interaction_mode:
                return await self._execute_with_progress(playbook_json, resolved_inputs, execution_id, workspace_id, profile_id, project_id)
            else:
                return await self._execute_with_minimal_ui(playbook_json, resolved_inputs, execution_id, workspace_id, profile_id, project_id)

        else:
            raise ValueError(f"Unknown playbook kind: {step.kind}")

    async def _execute_silently(
        self,
        playbook_json: PlaybookJson,
        inputs: Dict[str, Any],
        execution_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute playbook silently (system tool)"""
        return await self._execute_playbook_steps(playbook_json, inputs, execution_id, workspace_id, profile_id, project_id)

    async def _execute_with_minimal_ui(
        self,
        playbook_json: PlaybookJson,
        inputs: Dict[str, Any],
        execution_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute playbook with minimal UI feedback"""
        return await self._execute_playbook_steps(playbook_json, inputs, execution_id, workspace_id, profile_id, project_id)

    async def _execute_with_progress(
        self,
        playbook_json: PlaybookJson,
        inputs: Dict[str, Any],
        execution_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute playbook with progress feedback"""
        return await self._execute_playbook_steps(playbook_json, inputs, execution_id, workspace_id, profile_id, project_id)

    async def _execute_playbook_steps(
        self,
        playbook_json: PlaybookJson,
        playbook_inputs: Dict[str, Any],
        execution_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        project_id: Optional[str] = None
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
        # Create sandbox for execution (with or without project)
        sandbox_id = None
        logger.info(f"WorkflowOrchestrator._execute_playbook_steps: Starting execution. project_id={project_id}, workspace_id={workspace_id}, playbook_inputs keys: {list(playbook_inputs.keys())}")
        if workspace_id:
            try:
                from backend.app.services.sandbox.sandbox_manager import SandboxManager
                sandbox_manager = SandboxManager(self.store)

                if project_id:
                    # Create sandbox for project
                    try:
                        from backend.app.services.project.project_manager import ProjectManager
                        from backend.app.services.sandbox.playbook_integration import SandboxPlaybookAdapter
                        project_manager = ProjectManager(self.store)
                        logger.info(f"WorkflowOrchestrator: Getting project {project_id} for workspace {workspace_id}")
                        project_obj = await project_manager.get_project(project_id, workspace_id=workspace_id)
                        logger.info(f"WorkflowOrchestrator: project_obj={project_obj is not None}")
                        if project_obj:
                            logger.info(f"WorkflowOrchestrator: Playbook execution in Project mode: {project_id}")
                            sandbox_adapter = SandboxPlaybookAdapter(self.store)
                            try:
                                logger.info(f"WorkflowOrchestrator: Creating sandbox for project {project_id}")
                                sandbox_id = await sandbox_adapter.get_or_create_sandbox_for_project(
                                    project_id=project_id,
                                    workspace_id=workspace_id
                                )
                                logger.info(f"WorkflowOrchestrator: Using unified sandbox {sandbox_id} for project {project_id}")
                            except Exception as e:
                                logger.error(f"WorkflowOrchestrator: Failed to get unified sandbox: {e}", exc_info=True)
                        else:
                            logger.warning(f"WorkflowOrchestrator: Project {project_id} not found or doesn't belong to workspace {workspace_id}")
                    except Exception as e:
                        logger.error(f"WorkflowOrchestrator: Failed to create sandbox for project: {e}", exc_info=True)

                # If no sandbox created yet (no project or project sandbox creation failed), create execution sandbox
                if not sandbox_id:
                    try:
                        logger.info(f"WorkflowOrchestrator: Creating execution sandbox for workspace {workspace_id}")
                        sandbox_id = await sandbox_manager.create_sandbox(
                            sandbox_type="project_repo",
                            workspace_id=workspace_id,
                            context={"execution_id": execution_id, "playbook_code": getattr(playbook_json, 'playbook_code', None)}
                        )
                        logger.info(f"WorkflowOrchestrator: Created execution sandbox {sandbox_id}")
                    except Exception as e:
                        logger.error(f"WorkflowOrchestrator: Failed to create execution sandbox: {e}", exc_info=True)
            except Exception as e:
                logger.error(f"WorkflowOrchestrator: Failed to create sandbox: {e}", exc_info=True)
        else:
            logger.warning(f"WorkflowOrchestrator: No workspace_id provided, skipping sandbox creation")

        step_outputs = {}
        completed_steps = set()

        while len(completed_steps) < len(playbook_json.steps):
            ready_steps = self._get_ready_steps(
                playbook_json.steps,
                completed_steps,
                playbook_inputs,
                step_outputs
            )

            if not ready_steps:
                raise RuntimeError("Circular dependency or missing dependencies detected")

            for step in ready_steps:
                try:
                    step_index = len(completed_steps)
                    # Log playbook_inputs for debugging
                    logger.debug(f"WorkflowOrchestrator._execute_playbook_steps: Executing step {step.id}, playbook_inputs keys: {list(playbook_inputs.keys())}")
                    step_result = await self._execute_single_step(
                        step,
                        playbook_inputs,
                        step_outputs,
                        playbook_json.inputs,
                        execution_id=execution_id,
                        workspace_id=workspace_id,
                        profile_id=profile_id,
                        project_id=project_id,
                        step_index=step_index
                    )
                    step_outputs[step.id] = step_result
                    completed_steps.add(step.id)
                    step_result_keys = list(step_result.keys()) if isinstance(step_result, dict) else 'N/A'
                    step_result_preview = {}
                    if isinstance(step_result, dict):
                        for k, v in step_result.items():
                            if isinstance(v, (list, dict)):
                                step_result_preview[k] = f"{type(v).__name__}(len={len(v)})"
                            else:
                                step_result_preview[k] = str(v)[:100] if len(str(v)) > 100 else str(v)
                    logger.info(f"Step {step.id} completed successfully. Output keys: {step_result_keys}, Preview: {step_result_preview}")
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
                            error=str(e)
                        )
                    raise

        final_outputs = self._collect_final_outputs(
            playbook_json.outputs,
            step_outputs
        )

        # Create artifacts from output_artifacts definitions if available
        if execution_id and workspace_id and self.store:
            try:
                from backend.app.services.playbook_output_artifact_creator import PlaybookOutputArtifactCreator
                from backend.app.services.stores.artifacts_store import ArtifactsStore

                artifacts_store = ArtifactsStore(self.store.db_path)
                artifact_creator = PlaybookOutputArtifactCreator(artifacts_store)

                # Get playbook_code and metadata
                playbook_code = getattr(playbook_json, 'playbook_code', None)
                if not playbook_code:
                    # Try to get from playbook service
                    from backend.app.services.playbook_service import PlaybookService
                    playbook_service = PlaybookService(store=self.store)
                    # Need to find playbook_code from context or load playbook
                    logger.warning("Cannot determine playbook_code for artifact creation")
                    playbook_code = 'unknown'

                # Get playbook metadata (contains output_artifacts)
                playbook_metadata = {}
                if playbook_code and playbook_code != 'unknown':
                    from backend.app.services.playbook_service import PlaybookService
                    playbook_service = PlaybookService(store=self.store)
                    playbook = playbook_service.get_playbook(playbook_code)
                    if playbook and hasattr(playbook, 'metadata') and playbook.metadata:
                        # Convert metadata to dict
                        if hasattr(playbook.metadata, '__dict__'):
                            playbook_metadata = playbook.metadata.__dict__
                        elif isinstance(playbook.metadata, dict):
                            playbook_metadata = playbook.metadata
                        # Check for output_artifacts in playbook_json directly
                        if hasattr(playbook_json, 'output_artifacts'):
                            playbook_metadata['output_artifacts'] = playbook_json.output_artifacts

                # Also check playbook_json directly for output_artifacts (from JSON file)
                # PlaybookJson model doesn't have output_artifacts field, but JSON file does
                # So we need to load it from the JSON file directly
                if playbook_code and playbook_code != 'unknown':
                    try:
                        base_dir = Path(__file__).parent.parent.parent
                        playbook_json_path = base_dir / "playbooks" / "specs" / f"{playbook_code}.json"
                        if playbook_json_path.exists():
                            with open(playbook_json_path, 'r', encoding='utf-8') as f:
                                playbook_json_data = json.load(f)
                                if 'output_artifacts' in playbook_json_data:
                                    playbook_metadata['output_artifacts'] = playbook_json_data['output_artifacts']
                    except Exception as e:
                        logger.warning(f"Failed to load output_artifacts from JSON file: {e}")

                # Create artifacts
                if playbook_metadata.get('output_artifacts'):
                    # Build execution_context with sandbox_id if available
                    execution_context = {"execution_id": execution_id}
                    if sandbox_id:
                        execution_context["sandbox_id"] = sandbox_id
                        logger.info(f"🔍 WorkflowOrchestrator: Passing sandbox_id={sandbox_id} to artifact creator")
                    else:
                        logger.warning(f"🔍 WorkflowOrchestrator: No sandbox_id available for execution {execution_id}")

                    created_artifacts = await artifact_creator.create_artifacts_from_playbook_outputs(
                        playbook_code=playbook_code,
                        execution_id=execution_id,
                        workspace_id=workspace_id,
                        playbook_metadata=playbook_metadata,
                        step_outputs=step_outputs,
                        inputs=playbook_inputs,
                        execution_context=execution_context
                    )

                    if created_artifacts:
                        logger.info(f"Created {len(created_artifacts)} artifacts from playbook execution")
            except Exception as e:
                logger.error(f"Failed to create artifacts from playbook outputs: {e}", exc_info=True)
                # Don't fail the execution if artifact creation fails

            # Preserve sandbox_id in execution_context if available
            logger.error(f"🔍 Preserve sandbox_id check: sandbox_id={sandbox_id}, execution_id={execution_id}, workspace_id={workspace_id}")
            if sandbox_id and execution_id and workspace_id:
                try:
                    from backend.app.services.stores.tasks_store import TasksStore
                    tasks_store = TasksStore(db_path=self.store.db_path)
                    logger.error(f"🔍 Getting task by execution_id: {execution_id}")
                    task = tasks_store.get_task_by_execution_id(execution_id)
                    logger.error(f"🔍 Task found: {task is not None}")
                    if task:
                        execution_context = task.execution_context or {}
                        execution_context["sandbox_id"] = sandbox_id
                        logger.error(f"🔍 Updating task {task.id} with sandbox_id={sandbox_id}")
                        tasks_store.update_task(task.id, execution_context=execution_context)
                        logger.error(f"🔍 WorkflowOrchestrator: Preserved sandbox_id={sandbox_id} in execution_context for execution {execution_id}")
                    else:
                        logger.error(f"🔍 Task not found for execution_id: {execution_id}")
                except Exception as e:
                    logger.error(f"🔍 WorkflowOrchestrator: Failed to preserve sandbox_id in execution_context: {e}", exc_info=True)
            else:
                logger.error(f"🔍 Skipping sandbox_id preservation: sandbox_id={sandbox_id}, execution_id={execution_id}, workspace_id={workspace_id}")

        result = {
            'status': 'completed',
            'step_outputs': step_outputs,
            'outputs': final_outputs
        }

        # Include sandbox_id in result metadata so it can be saved by the caller
        if sandbox_id:
            result['sandbox_id'] = sandbox_id

        return result

    def _get_ready_steps(
        self,
        steps: List[Any],
        completed_steps: set,
        playbook_inputs: Optional[Dict[str, Any]] = None,
        step_outputs: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> List[Any]:
        """
        Get steps that are ready to execute (dependencies satisfied)

        Args:
            steps: List of steps to check
            completed_steps: Set of completed step IDs (will be modified if steps are skipped)
            playbook_inputs: Playbook inputs for condition evaluation
            step_outputs: Step outputs dict (will be updated with skipped steps)
        """
        ready = []
        for step in steps:
            if step.id in completed_steps:
                continue
            if all(dep in completed_steps for dep in step.depends_on):
                # Check condition if present
                if hasattr(step, 'condition') and step.condition:
                    # Build results dict for condition evaluation
                    results = {step_id: {'status': 'completed', 'outputs': {}} for step_id in completed_steps}
                    if not self._evaluate_condition(step, results, playbook_inputs):
                        logger.info(f"Step {step.id} condition not met, skipping")
                        # Mark step as completed (skipped) to avoid circular dependency
                        completed_steps.add(step.id)
                        # Record skipped status in step_outputs if provided
                        if step_outputs is not None:
                            step_outputs[step.id] = {
                                'status': 'skipped',
                                'reason': 'condition_not_met'
                            }
                        continue
                ready.append(step)
        return ready

    async def _execute_single_step_iteration(
        self,
        step: Any,
        playbook_inputs: Dict[str, Any],
        step_outputs: Dict[str, Dict[str, Any]],
        playbook_input_defs: Dict[str, Any],
        execution_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        project_id: Optional[str] = None,
        step_index: int = 0
    ) -> Dict[str, Any]:
        """Execute a single step iteration (used by loop handler)"""
        # Mark step as in loop iteration to prevent recursion
        step._in_loop_iteration = True
        try:
            return await self._execute_single_step(
                step,
                playbook_inputs,
                step_outputs,
                playbook_input_defs,
                execution_id=execution_id,
                workspace_id=workspace_id,
                profile_id=profile_id,
                project_id=project_id,
                step_index=step_index
            )
        finally:
            # Clean up the flag
            if hasattr(step, '_in_loop_iteration'):
                delattr(step, '_in_loop_iteration')

    async def _execute_single_step(
        self,
        step: Any,
        playbook_inputs: Dict[str, Any],
        step_outputs: Dict[str, Dict[str, Any]],
        playbook_input_defs: Dict[str, Any],
        execution_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        project_id: Optional[str] = None,
        step_index: int = 0
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
        step_started_at = datetime.utcnow()

        if execution_id and workspace_id and self.store:
            self._create_step_event(
                execution_id=execution_id,
                workspace_id=workspace_id,
                profile_id=profile_id,
                step_id=step.id,
                step_name=step.id,
                step_index=step_index,
                status="running",
                started_at=step_started_at
            )

        try:
            # Check if step has for_each (loop support)
            # Only handle for_each at the top level, not in iterations
            if hasattr(step, 'for_each') and step.for_each and not hasattr(step, '_in_loop_iteration'):
                # Execute step for each item in the array using loop handler
                return await self.step_loop.execute_step_with_loop(
                    step,
                    self._execute_single_step_iteration,
                    playbook_inputs,
                    step_outputs,
                    playbook_input_defs,
                    execution_id=execution_id,
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    project_id=project_id,
                    step_index=step_index
                )

            # Add workspace_id to playbook_inputs for template resolution
            # This allows {{workspace_id}} template variable to be resolved
            playbook_inputs_with_context = playbook_inputs.copy()
            if workspace_id:
                playbook_inputs_with_context['workspace_id'] = workspace_id

            resolved_inputs = self.template_engine.prepare_playbook_inputs(
                step,
                playbook_inputs_with_context,
                step_outputs
            )

            # Resolve tool: support both legacy 'tool' field and new 'tool_slot' field
            tool_id = None
            if hasattr(step, 'tool_slot') and step.tool_slot:
                # New slot-based mode: resolve slot to tool_id
                slot_resolver = get_tool_slot_resolver(store=self.store)
                try:
                    tool_id = await slot_resolver.resolve(
                        slot=step.tool_slot,
                        workspace_id=workspace_id or "",
                        project_id=project_id  # Use project_id from execution context
                    )
                    logger.info(f"Resolved tool slot '{step.tool_slot}' to tool '{tool_id}'")
                except SlotNotFoundError as e:
                    logger.error(f"Failed to resolve tool slot '{step.tool_slot}': {e}")
                    raise ValueError(f"Tool slot '{step.tool_slot}' not configured. Please set up a mapping in workspace settings.")
            elif hasattr(step, 'tool') and step.tool:
                # Legacy mode: use tool field directly
                tool_id = step.tool
                logger.debug(f"Using legacy tool field: '{tool_id}'")
            else:
                raise ValueError("PlaybookStep must have either 'tool' (legacy) or 'tool_slot' (recommended) field")

            # Check policy constraints if tool_policy is specified
            if hasattr(step, 'tool_policy') and step.tool_policy:
                policy_engine = get_tool_policy_engine()
                try:
                    policy_engine.check(
                        tool_id=tool_id,
                        policy=step.tool_policy,
                        workspace_id=workspace_id
                    )
                except PolicyViolationError as e:
                    logger.error(f"Tool '{tool_id}' violates policy: {e}")
                    raise ValueError(f"Tool execution blocked by policy: {str(e)}")

            # Execute tool - pass profile_id only for tools that need it (e.g., LLM tools)
            tool_inputs = resolved_inputs.copy()
            # Only add profile_id for core_llm tools or tools that explicitly require it
            if profile_id and (tool_id.startswith('core_llm.') or 'llm' in tool_id.lower()):
                tool_inputs['profile_id'] = profile_id

            tool_result = await self.tool_executor.execute_tool(
                tool_id,
                **tool_inputs
            )

            step_output = {}
            for output_name, tool_field in step.outputs.items():
                if isinstance(tool_result, dict):
                    # Handle empty tool_field (use entire tool_result)
                    if not tool_field or tool_field == "":
                        value = tool_result
                        logger.debug(f"Step {step.id} output mapping: output_name={output_name}, using entire tool_result (len={len(tool_result)})")
                    else:
                        # Handle dot-separated field paths (e.g., "extracted_data.topics")
                        value = tool_result
                        tool_result_keys = list(tool_result.keys()) if isinstance(tool_result, dict) else 'N/A'
                        logger.debug(f"Step {step.id} output mapping: output_name={output_name}, tool_field={tool_field}, tool_result_keys={tool_result_keys}")
                        for field_part in tool_field.split('.'):
                            if isinstance(value, dict):
                                value = value.get(field_part)
                                logger.debug(f"Step {step.id} output mapping: field_part={field_part}, value_type={type(value).__name__ if value is not None else 'None'}")
                            else:
                                value = None
                                break
                            if value is None:
                                break

                        if value is None:
                            logger.warning(f"Step {step.id} output mapping failed: output_name={output_name}, tool_field={tool_field} not found in tool_result")
                        else:
                            value_preview = f"{type(value).__name__}(len={len(value)})" if isinstance(value, (list, dict)) else str(value)[:100]
                            logger.debug(f"Step {step.id} output mapping success: {output_name}={value_preview}")
                    step_output[output_name] = value
                else:
                    step_output[output_name] = tool_result

            step_completed_at = datetime.utcnow()

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
                    completed_at=step_completed_at
                )

            return step_output
        except Exception as e:
            step_completed_at = datetime.utcnow()
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
                    error=str(e)
                )
            raise

    def _collect_final_outputs(
        self,
        output_defs: Dict[str, Any],
        step_outputs: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Collect final playbook outputs from step outputs

        Args:
            output_defs: Playbook output definitions
            step_outputs: All step outputs

        Returns:
            Final playbook outputs
        """
        final_outputs = {}
        for output_name, output_def in output_defs.items():
            source_path = output_def.source
            parts = source_path.split('.')
            if len(parts) >= 3 and parts[0] == 'step':
                step_id = parts[1]
                output_key = '.'.join(parts[2:])
                if step_id in step_outputs:
                    final_outputs[output_name] = step_outputs[step_id].get(output_key)
        return final_outputs

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
        error: Optional[str] = None
    ):
        """Create PLAYBOOK_STEP event for step timeline"""
        if not self.store:
            return

        try:
            from backend.app.models.mindscape import MindEvent, EventType, EventActor

            event = MindEvent(
                id=str(uuid.uuid4()),
                timestamp=datetime.utcnow(),
                actor=EventActor.SYSTEM,
                channel="workflow_orchestrator",
                profile_id=profile_id or "default-user",
                project_id=None,
                workspace_id=workspace_id,
                event_type=EventType.PLAYBOOK_STEP,
                payload={
                    "execution_id": execution_id,
                    "step_id": step_id,
                    "step_name": step_name,
                    "step_index": step_index,
                    "status": status,
                    "started_at": started_at.isoformat() if started_at else None,
                    "completed_at": completed_at.isoformat() if completed_at else None,
                    "error": error
                },
                entity_ids=[execution_id, step_id],
                metadata={}
            )

            self.store.create_event(event, generate_embedding=False)
            logger.debug(f"Created PLAYBOOK_STEP event for step {step_id} (index {step_index})")
        except Exception as e:
            logger.warning(f"Failed to create PLAYBOOK_STEP event: {e}")

    async def _execute_step_with_retry(
        self,
        step: WorkflowStep,
        workflow_context: Dict[str, Any],
        previous_results: Dict[str, Dict[str, Any]],
        execution_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        project_id: Optional[str] = None,
        step_index: int = 0
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
        retry_policy = step.retry_policy
        if not retry_policy:
            retry_policy = self._get_default_retry_policy(step.kind)

        last_error = None
        for attempt in range(retry_policy.max_retries + 1):
            try:
                if attempt > 0:
                    delay = self._calculate_retry_delay(attempt, retry_policy)
                    logger.info(f"Retrying step {step.playbook_code} (attempt {attempt + 1}/{retry_policy.max_retries + 1}) after {delay}s")
                    import asyncio
                    await asyncio.sleep(delay)

                result = await self.execute_workflow_step(
                    step,
                    workflow_context,
                    previous_results,
                    execution_id=execution_id,
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    project_id=project_id,
                    step_index=step_index
                )

                if result.get('status') == 'completed':
                    if attempt > 0:
                        logger.info(f"Step {step.playbook_code} succeeded after {attempt} retries")
                    return result

                last_error = result.get('error', 'Unknown error')
                error_type = self._classify_error(last_error)

                if retry_policy.retryable_errors and error_type not in retry_policy.retryable_errors:
                    logger.warning(f"Error type {error_type} is not retryable for step {step.playbook_code}")
                    return result

            except Exception as e:
                last_error = str(e)
                error_type = self._classify_error(last_error)
                logger.warning(f"Step {step.playbook_code} failed (attempt {attempt + 1}/{retry_policy.max_retries + 1}): {e}")

                if retry_policy.retryable_errors and error_type not in retry_policy.retryable_errors:
                    logger.warning(f"Error type {error_type} is not retryable for step {step.playbook_code}")
                    return {
                        'status': 'error',
                        'error': last_error,
                        'error_type': error_type,
                        'attempts': attempt + 1,
                        'retries_exhausted': False
                    }

                if attempt < retry_policy.max_retries:
                    continue
                else:
                    return {
                        'status': 'error',
                        'error': last_error,
                        'error_type': error_type,
                        'attempts': attempt + 1,
                        'retries_exhausted': True
                    }

        return {
            'status': 'error',
            'error': last_error or 'Unknown error',
            'attempts': retry_policy.max_retries + 1,
            'retries_exhausted': True
        }

    def _get_default_retry_policy(self, kind: PlaybookKind) -> RetryPolicy:
        """Get default retry policy based on playbook kind"""
        if kind == PlaybookKind.SYSTEM_TOOL:
            return RetryPolicy(
                max_retries=3,
                retry_delay=1.0,
                exponential_backoff=True,
                retryable_errors=[]
            )
        else:
            return RetryPolicy(
                max_retries=1,
                retry_delay=2.0,
                exponential_backoff=False,
                retryable_errors=[]
            )

    def _calculate_retry_delay(self, attempt: int, retry_policy: RetryPolicy) -> float:
        """Calculate retry delay based on attempt number and policy"""
        if retry_policy.exponential_backoff:
            return retry_policy.retry_delay * (2 ** (attempt - 1))
        else:
            return retry_policy.retry_delay

    def _classify_error(self, error: str) -> str:
        """Classify error type for retry decision"""
        error_lower = error.lower()
        if 'timeout' in error_lower or 'timed out' in error_lower:
            return 'timeout'
        elif 'network' in error_lower or 'connection' in error_lower:
            return 'network'
        elif 'rate limit' in error_lower or 'quota' in error_lower:
            return 'rate_limit'
        elif 'not found' in error_lower or 'missing' in error_lower:
            return 'not_found'
        elif 'permission' in error_lower or 'unauthorized' in error_lower:
            return 'permission'
        elif 'validation' in error_lower or 'invalid' in error_lower:
            return 'validation'
        else:
            return 'unknown'

