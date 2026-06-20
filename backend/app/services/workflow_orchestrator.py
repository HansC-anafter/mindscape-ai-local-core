"""
Workflow Orchestrator

Executes multi-step workflows based on HandoffPlan and playbook.json.
Manages step dependencies, template resolution, and tool execution.
"""

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
from backend.app.services.execution_core.errors import RecoverableStepError
from backend.app.services.workflow.handoff_execution import (
    execute_handoff_workflow_for_orchestrator as workflow_execute_handoff_workflow,
)
from backend.app.services.workflow.playbook_execution import (
    execute_playbook_steps_for_orchestrator as workflow_execute_playbook_steps,
    execute_single_step_for_orchestrator as workflow_execute_single_step,
    execute_single_step_iteration_for_orchestrator as workflow_execute_single_step_iteration,
)
from backend.app.services.workflow.orchestrator_runtime_methods import (
    WorkflowOrchestratorRuntimeMethods,
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
)
from backend.app.services.workflow.scheduling import (
    build_dependency_graph as workflow_build_dependency_graph,
    evaluate_condition as workflow_evaluate_condition,
    get_nested_value as workflow_get_nested_value,
    get_ready_steps as workflow_get_ready_steps,
    get_ready_steps_for_parallel as workflow_get_ready_steps_for_parallel,
    has_output as workflow_has_output,
)
from backend.app.services.workflow.step_runner import (
    execute_workflow_step as workflow_execute_workflow_step,
)

class WorkflowOrchestrator(WorkflowOrchestratorRuntimeMethods):
    """Orchestrates multi-step workflow execution"""

    def __init__(self, store=None):
        self.tool_executor = ToolExecutor()
        self.template_engine = TemplateEngine()
        self.step_loop = WorkflowStepLoop(
            self.template_engine, self.tool_executor, store
        )
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
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute workflow from HandoffPlan with parallel execution support

        Args:
            handoff_plan: HandoffPlan with workflow steps

        Returns:
            Dict with execution results for each step
        """
        return await workflow_execute_handoff_workflow(
            self,
            handoff_plan,
            execution_id=execution_id,
            workspace_id=workspace_id,
            profile_id=profile_id,
            project_id=project_id,
        )

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
        return await workflow_execute_playbook_steps(
            self,
            playbook_json,
            playbook_inputs=playbook_inputs,
            execution_id=execution_id,
            workspace_id=workspace_id,
            profile_id=profile_id,
            project_id=project_id,
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
        return await workflow_execute_single_step_iteration(
            self,
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
        return await workflow_execute_single_step(
            self,
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
