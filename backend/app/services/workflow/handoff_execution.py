"""Handoff workflow execution helpers for the WorkflowOrchestrator facade."""

import asyncio
import logging
from typing import Any, Dict, Optional, Set

from backend.app.models.playbook import HandoffPlan
from backend.app.services.workflow.scheduling import (
    apply_step_result_to_context,
    build_paused_workflow_result,
    build_previous_results,
    normalize_parallel_step_result,
    should_stop_workflow_after_error,
)

logger = logging.getLogger(__name__)


async def execute_handoff_workflow_for_orchestrator(
    orchestrator: Any,
    handoff_plan: HandoffPlan,
    execution_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    profile_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute a HandoffPlan through the existing WorkflowOrchestrator facade."""
    results = {}
    workflow_context = handoff_plan.context.copy()
    playbook_inputs = workflow_context.copy()

    dependency_graph = orchestrator._build_dependency_graph(handoff_plan.steps)
    completed_steps: Set[str] = set()
    pending_steps = {step.playbook_code: step for step in handoff_plan.steps}

    while pending_steps:
        ready_steps = orchestrator._get_ready_steps_for_parallel(
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
            f"Executing {len(ready_steps)} steps in parallel: "
            f"{[s.playbook_code for s in ready_steps]}"
        )

        previous_results = build_previous_results(results)

        step_tasks = [
            orchestrator._execute_step_with_retry(
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
            step_result = normalize_parallel_step_result(
                step_playbook_code=step.playbook_code,
                step_result=step_result,
            )
            results[step.playbook_code] = step_result
            completed_steps.add(step.playbook_code)
            del pending_steps[step.playbook_code]

            if isinstance(step_result, dict) and step_result.get("status") == "paused":
                return build_paused_workflow_result(
                    step_playbook_code=step.playbook_code,
                    results=results,
                    workflow_context=workflow_context,
                    step_result=step_result,
                )

            apply_step_result_to_context(
                workflow_context=workflow_context,
                step_result=step_result,
            )

            if should_stop_workflow_after_error(
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
