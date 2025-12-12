"""
Simple Runtime - Default runtime implementation

Wraps existing WorkflowOrchestrator to provide RuntimePort interface.
Used for simple execution mode (no resume, no human approval).
"""

import logging
from typing import Dict, Any, Optional

from backend.app.core.runtime_port import (
    RuntimePort,
    ExecutionProfile,
    ExecutionResult
)
from backend.app.core.execution_context import ExecutionContext
from backend.app.services.workflow_orchestrator import WorkflowOrchestrator
from backend.app.models.playbook import (
    PlaybookRun,
    HandoffPlan,
    WorkflowStep,
    PlaybookKind,
    InteractionMode
)

logger = logging.getLogger(__name__)


class SimpleRuntime(RuntimePort):
    """Default simple runtime (wraps existing WorkflowOrchestrator)"""

    def __init__(self, store=None):
        """
        Initialize SimpleRuntime

        Args:
            store: MindscapeStore instance (optional)
        """
        self.orchestrator = WorkflowOrchestrator(store=store)
        self.store = store

    @property
    def name(self) -> str:
        """Runtime name"""
        return "simple"

    def supports(self, execution_profile: ExecutionProfile) -> bool:
        """
        Simple runtime supports simple execution mode

        Args:
            execution_profile: ExecutionProfile to check

        Returns:
            True if profile matches simple mode requirements
        """
        return (
            execution_profile.execution_mode == "simple" and
            not execution_profile.supports_resume and
            not execution_profile.requires_human_approval
        )

    async def execute(
        self,
        playbook_run: PlaybookRun,
        context: ExecutionContext,
        inputs: Optional[Dict[str, Any]] = None
    ) -> ExecutionResult:
        """
        Execute using WorkflowOrchestrator

        Args:
            playbook_run: PlaybookRun instance
            context: ExecutionContext
            inputs: Optional input parameters

        Returns:
            ExecutionResult with execution status and outputs
        """
        try:
            # Check if playbook has JSON (required for WorkflowOrchestrator)
            if not playbook_run.has_json():
                # If no JSON, this should use PlaybookRunner instead
                # But for now, we'll return an error
                return ExecutionResult(
                    status="failed",
                    execution_id=context.tags.get("execution_id", "unknown") if context.tags else "unknown",
                    outputs={},
                    error="SimpleRuntime requires playbook.json. Use PlaybookRunner for playbook.md only.",
                    metadata={"runtime": "simple"}
                )

            # Convert playbook_run to HandoffPlan
            handoff_plan = self._convert_to_handoff_plan(playbook_run, inputs or {})

            # Get execution_id from context tags or generate one
            execution_id = context.tags.get("execution_id") if context.tags else None
            profile_id = context.actor_id

            # Execute using orchestrator
            result = await self.orchestrator.execute_workflow(
                handoff_plan=handoff_plan,
                execution_id=execution_id,
                workspace_id=context.workspace_id,
                profile_id=profile_id
            )

            # Determine status from result
            status = "completed"
            error = None
            if result.get("status") == "error" or result.get("error"):
                status = "failed"
                error = result.get("error") or "Execution failed"

            # Extract outputs from result context
            outputs = result.get("context", {})
            if "steps" in result:
                # If result has steps, extract outputs from each step
                step_outputs = {}
                for step_code, step_result in result.get("steps", {}).items():
                    if step_result.get("outputs"):
                        step_outputs[step_code] = step_result["outputs"]
                if step_outputs:
                    outputs = step_outputs

            return ExecutionResult(
                status=status,
                execution_id=execution_id or "unknown",
                outputs=outputs,
                error=error,
                metadata={
                    "runtime": "simple",
                    "steps_completed": len(result.get("steps", {}))
                }
            )

        except Exception as e:
            logger.error(f"SimpleRuntime execution failed: {e}", exc_info=True)
            execution_id = context.tags.get("execution_id", "unknown") if context.tags else "unknown"
            return ExecutionResult(
                status="failed",
                execution_id=execution_id,
                outputs={},
                error=str(e),
                metadata={"runtime": "simple"}
            )

    async def resume(
        self,
        execution_id: str,
        checkpoint: Dict[str, Any]
    ) -> ExecutionResult:
        """
        Simple runtime does not support resume

        Args:
            execution_id: Execution ID
            checkpoint: Checkpoint data

        Raises:
            NotImplementedError: Simple runtime does not support resume
        """
        raise NotImplementedError("Simple runtime does not support resume")

    async def pause(
        self,
        execution_id: str
    ) -> ExecutionResult:
        """
        Simple runtime does not support pause

        Args:
            execution_id: Execution ID to pause

        Raises:
            NotImplementedError: Simple runtime does not support pause
        """
        raise NotImplementedError("Simple runtime does not support pause")

    async def cancel(
        self,
        execution_id: str,
        reason: Optional[str] = None
    ) -> ExecutionResult:
        """
        Cancel execution

        Args:
            execution_id: Execution ID to cancel
            reason: Optional cancellation reason

        Returns:
            ExecutionResult with cancellation status
        """
        # Simple runtime: mark as cancelled
        return ExecutionResult(
            status="failed",
            execution_id=execution_id,
            outputs={},
            error=f"Execution cancelled: {reason or 'User requested'}" if reason else "Execution cancelled",
            metadata={"runtime": "simple", "cancelled": True}
        )

    async def get_status(
        self,
        execution_id: str
    ) -> ExecutionResult:
        """
        Get execution status

        Args:
            execution_id: Execution ID

        Returns:
            ExecutionResult with current status
        """
        # Simple runtime: query from task store if available
        if self.store:
            try:
                from backend.app.services.stores.tasks_store import TasksStore
                tasks_store = TasksStore(self.store.db_path)
                task = tasks_store.get_task(execution_id)
                if task:
                    status = "completed" if task.status.value == "succeeded" else "failed" if task.status.value == "failed" else "running"
                    return ExecutionResult(
                        status=status,
                        execution_id=execution_id,
                        outputs=task.execution_context.get("outputs", {}) if task.execution_context else {},
                        error=task.error,
                        metadata={"runtime": "simple"}
                    )
            except Exception as e:
                logger.warning(f"Failed to get task status: {e}")

        return ExecutionResult(
            status="unknown",
            execution_id=execution_id,
            outputs={},
            metadata={"runtime": "simple"}
        )

    @property
    def capabilities(self) -> list[str]:
        """Runtime capabilities"""
        return ["simple_execution", "parallel_steps"]

    def _convert_to_handoff_plan(
        self,
        playbook_run: PlaybookRun,
        inputs: Dict[str, Any]
    ) -> HandoffPlan:
        """
        Convert PlaybookRun to HandoffPlan

        Args:
            playbook_run: PlaybookRun instance
            inputs: Input parameters

        Returns:
            HandoffPlan for WorkflowOrchestrator
        """
        if not playbook_run.playbook_json:
            raise ValueError("Cannot convert PlaybookRun to HandoffPlan: playbook_json is None")

        # Create workflow steps from playbook.json steps
        workflow_steps = []
        for step in playbook_run.playbook_json.steps:
            # Determine playbook kind from playbook metadata
            kind = playbook_run.playbook.metadata.kind if playbook_run.playbook.metadata else PlaybookKind.USER_WORKFLOW

            # Get interaction mode from playbook metadata
            interaction_modes = (
                playbook_run.playbook.metadata.interaction_mode
                if playbook_run.playbook.metadata
                else [InteractionMode.CONVERSATIONAL]
            )

            workflow_step = WorkflowStep(
                playbook_code=step.tool,  # In playbook.json, tool is the playbook_code
                kind=kind,
                inputs=step.inputs,
                input_mapping=step.outputs,  # Map outputs to next step inputs
                interaction_mode=interaction_modes
            )
            workflow_steps.append(workflow_step)

        # Create HandoffPlan
        handoff_plan = HandoffPlan(
            steps=workflow_steps,
            context=inputs
        )

        return handoff_plan
