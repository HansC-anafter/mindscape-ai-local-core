"""
Workflow Orchestrator

Executes multi-step workflows based on HandoffPlan and playbook.json.
Manages step dependencies, template resolution, and tool execution.
"""

import json
import logging
import asyncio
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

logger = logging.getLogger(__name__)


class WorkflowOrchestrator:
    """Orchestrates multi-step workflow execution"""

    def __init__(self):
        self.tool_executor = ToolExecutor()
        self.template_engine = TemplateEngine()

    def load_playbook_json(self, playbook_code: str) -> Optional[PlaybookJson]:
        """
        Load playbook.json file

        Args:
            playbook_code: Playbook code

        Returns:
            PlaybookJson model or None if not found
        """
        base_dir = Path(__file__).parent.parent.parent
        playbook_json_path = base_dir / "playbooks" / f"{playbook_code}.json"

        if not playbook_json_path.exists():
            logger.warning(f"playbook.json not found: {playbook_json_path}")
            return None

        try:
            with open(playbook_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return PlaybookJson(**data)
        except Exception as e:
            logger.error(f"Failed to load playbook.json: {e}")
            return None

    async def execute_workflow(
        self,
        handoff_plan: HandoffPlan
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
                    previous_results
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
        results: Dict[str, Dict[str, Any]]
    ) -> bool:
        """
        Evaluate condition for workflow step

        Args:
            step: WorkflowStep with optional condition
            results: Current execution results

        Returns:
            True if step should execute, False if should skip
        """
        if not step.condition:
            return True

        try:
            condition = step.condition.strip()

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
        previous_results: Dict[str, Dict[str, Any]]
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

        if step.kind == PlaybookKind.SYSTEM_TOOL:
            if InteractionMode.SILENT in step.interaction_mode:
                return await self._execute_silently(playbook_json, resolved_inputs)
            else:
                return await self._execute_with_minimal_ui(playbook_json, resolved_inputs)

        elif step.kind == PlaybookKind.USER_WORKFLOW:
            if InteractionMode.NEEDS_REVIEW in step.interaction_mode:
                logger.info(f"Step {step.playbook_code} requires review")
            if InteractionMode.CONVERSATIONAL in step.interaction_mode:
                return await self._execute_with_progress(playbook_json, resolved_inputs)
            else:
                return await self._execute_with_minimal_ui(playbook_json, resolved_inputs)

        else:
            raise ValueError(f"Unknown playbook kind: {step.kind}")

    async def _execute_silently(
        self,
        playbook_json: PlaybookJson,
        inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute playbook silently (system tool)"""
        return await self._execute_playbook_steps(playbook_json, inputs)

    async def _execute_with_minimal_ui(
        self,
        playbook_json: PlaybookJson,
        inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute playbook with minimal UI feedback"""
        return await self._execute_playbook_steps(playbook_json, inputs)

    async def _execute_with_progress(
        self,
        playbook_json: PlaybookJson,
        inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute playbook with progress feedback"""
        return await self._execute_playbook_steps(playbook_json, inputs)

    async def _execute_playbook_steps(
        self,
        playbook_json: PlaybookJson,
        playbook_inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute all steps in playbook.json

        Args:
            playbook_json: PlaybookJson definition
            playbook_inputs: Resolved playbook inputs

        Returns:
            Dict with step outputs and final playbook outputs
        """
        step_outputs = {}
        completed_steps = set()

        while len(completed_steps) < len(playbook_json.steps):
            ready_steps = self._get_ready_steps(
                playbook_json.steps,
                completed_steps
            )

            if not ready_steps:
                raise RuntimeError("Circular dependency or missing dependencies detected")

            for step in ready_steps:
                try:
                    step_result = await self._execute_single_step(
                        step,
                        playbook_inputs,
                        step_outputs,
                        playbook_json.inputs
                    )
                    step_outputs[step.id] = step_result
                    completed_steps.add(step.id)
                    logger.debug(f"Step {step.id} completed successfully")
                except Exception as e:
                    logger.error(f"Step {step.id} failed: {e}", exc_info=True)
                    raise

        final_outputs = self._collect_final_outputs(
            playbook_json.outputs,
            step_outputs
        )

        return {
            'status': 'completed',
            'step_outputs': step_outputs,
            'outputs': final_outputs
        }

    def _get_ready_steps(
        self,
        steps: List[Any],
        completed_steps: set
    ) -> List[Any]:
        """Get steps that are ready to execute (dependencies satisfied)"""
        ready = []
        for step in steps:
            if step.id in completed_steps:
                continue
            if all(dep in completed_steps for dep in step.depends_on):
                ready.append(step)
        return ready

    async def _execute_single_step(
        self,
        step: Any,
        playbook_inputs: Dict[str, Any],
        step_outputs: Dict[str, Dict[str, Any]],
        playbook_input_defs: Dict[str, Any]
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
        resolved_inputs = self.template_engine.prepare_playbook_inputs(
            step,
            playbook_inputs,
            step_outputs
        )

        tool_result = await self.tool_executor.execute_tool(
            step.tool,
            **resolved_inputs
        )

        step_output = {}
        for output_name, tool_field in step.outputs.items():
            if isinstance(tool_result, dict):
                step_output[output_name] = tool_result.get(tool_field)
            else:
                step_output[output_name] = tool_result

        return step_output

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

    async def _execute_step_with_retry(
        self,
        step: WorkflowStep,
        workflow_context: Dict[str, Any],
        previous_results: Dict[str, Dict[str, Any]]
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
                    previous_results
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

