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
from backend.app.core.domain_context import LocalDomainContext
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

    # Best-effort support flags (used by RuntimeFactory scoring)
    supports_resume: bool = True
    supports_human_approval: bool = True

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
        # Best-effort: allow SimpleRuntime to run workflow playbooks even when they request
        # resume/human approval. We implement a lightweight pause/resume with checkpoints.
        return execution_profile.execution_mode in {"simple", "durable"}

    async def execute(
        self,
        playbook_run: PlaybookRun,
        context: LocalDomainContext,
        inputs: Optional[Dict[str, Any]] = None
    ) -> ExecutionResult:
        """
        Execute using WorkflowOrchestrator

        Args:
            playbook_run: PlaybookRun instance
            context: LocalDomainContext
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

            # Get playbook_code from context tags (passed from executor) or playbook metadata
            playbook_code_from_context = context.tags.get("playbook_code") if context.tags else None

            # Convert playbook_run to HandoffPlan
            # Ensure inputs are properly passed to workflow_context
            playbook_inputs = inputs or {}
            logger.info(f"SimpleRuntime: playbook_inputs keys: {list(playbook_inputs.keys())}")
            handoff_plan = self._convert_to_handoff_plan(playbook_run, playbook_inputs, playbook_code_from_context)
            # Keep inputs in handoff_plan.context for placeholder rendering.
            if playbook_inputs:
                handoff_plan.context.update(playbook_inputs)
                logger.info(f"SimpleRuntime: Updated handoff_plan.context with inputs. Context keys: {list(handoff_plan.context.keys())}")

            # Get execution_id from context tags or generate one
            execution_id = context.tags.get("execution_id") if context.tags else None
            profile_id = context.actor_id
            project_id = context.tags.get("project_id") if context.tags else None
            # Handle empty string as None
            if project_id == "":
                project_id = None

            logger.info(f"SimpleRuntime: Extracted project_id={project_id} from context.tags={context.tags}")

            # Execute using orchestrator
            logger.info(f"SimpleRuntime: Executing workflow with handoff_plan.steps count: {len(handoff_plan.steps)}, project_id={project_id}")
            result = await self.orchestrator.execute_workflow(
                handoff_plan=handoff_plan,
                execution_id=execution_id,
                workspace_id=context.workspace_id,
                profile_id=profile_id,
                project_id=project_id
            )

            # Log result structure for debugging
            logger.info(f"SimpleRuntime: orchestrator result keys: {list(result.keys())}")
            logger.info(f"SimpleRuntime: orchestrator result['steps'] keys: {list(result.get('steps', {}).keys())}")
            logger.info(f"SimpleRuntime: orchestrator result['steps'] count: {len(result.get('steps', {}))}")

            # Determine status from result
            status = "completed"
            error = None
            checkpoint = None
            if isinstance(result, dict) and result.get("status") == "paused":
                status = "paused"
                checkpoint = result.get("checkpoint")
            elif result.get("status") == "error" or result.get("error"):
                status = "failed"
                error = result.get("error") or "Execution failed"

            # Extract outputs from result context
            outputs = result.get("context", {}) if isinstance(result, dict) else {}
            steps_info = result.get("steps", {}) if isinstance(result, dict) else {}

            if steps_info:
                for _, step_result in steps_info.items():
                    if isinstance(step_result, dict):
                        step_status = step_result.get("status")
                        if step_status in ["error", "failed", "FAILED"]:
                            status = "failed"
                            error = step_result.get("error") or "Execution failed"
                            break

            # Log steps info for debugging
            logger.info(f"SimpleRuntime: steps_info keys: {list(steps_info.keys()) if steps_info else 'empty'}")
            logger.info(f"SimpleRuntime: steps_info count: {len(steps_info)}")
            if steps_info:
                for step_code, step_result in steps_info.items():
                    logger.info(f"SimpleRuntime: step_code={step_code}, step_result type={type(step_result)}, step_result keys={list(step_result.keys()) if isinstance(step_result, dict) else 'not dict'}")

            if "steps" in result:
                # If result has steps, extract outputs from each step
                step_outputs = {}
                for step_code, step_result in result.get("steps", {}).items():
                    logger.debug(f"SimpleRuntime: step_code={step_code}, step_result keys={list(step_result.keys()) if isinstance(step_result, dict) else 'not dict'}")
                    # step_result may contain 'step_outputs' (from _execute_playbook_steps) or 'outputs'
                    if isinstance(step_result, dict):
                        # Check for step_outputs first (from _execute_playbook_steps)
                        if step_result.get("step_outputs"):
                            step_outputs[step_code] = step_result["step_outputs"]
                        elif step_result.get("outputs"):
                            step_outputs[step_code] = step_result["outputs"]
                if step_outputs:
                    outputs = step_outputs

                    # Extract sandbox_id from result if available
                    sandbox_id = None
                    # First check if sandbox_id is in result directly (from _execute_playbook_steps)
                    if isinstance(result, dict) and 'sandbox_id' in result:
                        sandbox_id = result['sandbox_id']
                        logger.info(f"SimpleRuntime: Found sandbox_id in result: {sandbox_id}")
                    # Then check in steps
                    elif "steps" in result:
                        for step_code, step_result in result.get("steps", {}).items():
                            if isinstance(step_result, dict) and 'sandbox_id' in step_result:
                                sandbox_id = step_result['sandbox_id']
                                logger.info(f"SimpleRuntime: Found sandbox_id in step {step_code}: {sandbox_id}")
                                break

                    metadata = {
                        "runtime": "simple",
                        "steps_completed": len(steps_info),
                        "steps": steps_info  # Preserve full step information
                    }
                    if sandbox_id:
                        metadata["sandbox_id"] = sandbox_id

                    return ExecutionResult(
                        status=status,
                        execution_id=execution_id or "unknown",
                        outputs=outputs,
                        checkpoint=checkpoint,
                        error=error,
                        metadata=metadata
                    )

            # Fallback: return best-effort outputs even if step_outputs is empty.
            metadata = {
                "runtime": "simple",
                "steps_completed": len(steps_info),
                "steps": steps_info
            }
            return ExecutionResult(
                status=status,
                execution_id=execution_id or "unknown",
                outputs=outputs,
                checkpoint=checkpoint,
                error=error,
                metadata=metadata
            )

        except Exception as e:
            logger.error(f"SimpleRuntime execution failed: {e}", exc_info=True)
            import traceback
            error_details = traceback.format_exc()
            execution_id = context.tags.get("execution_id", "unknown") if context.tags else "unknown"
            return ExecutionResult(
                status="failed",
                execution_id=execution_id,
                outputs={},
                error=str(e),
                metadata={
                    "runtime": "simple",
                    "error_details": error_details
                }
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
        inputs: Dict[str, Any],
        playbook_code: Optional[str] = None
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

        # For playbook.json with tool steps, we should NOT convert to HandoffPlan
        # Instead, the orchestrator should execute playbook.json steps directly
        # This method should only be used for multi-playbook workflows (HandoffPlan)
        # For single playbook execution, use _execute_playbook_steps instead

        # Create a single WorkflowStep for the entire playbook
        # The orchestrator will handle executing the internal steps
        kind = playbook_run.playbook.metadata.kind if playbook_run.playbook.metadata else PlaybookKind.USER_WORKFLOW
        interaction_modes = (
            playbook_run.playbook.metadata.interaction_mode
            if playbook_run.playbook.metadata
            else [InteractionMode.CONVERSATIONAL]
        )

        # Get playbook_code from parameter, playbook.metadata, or playbook_json
        if not playbook_code:
            if playbook_run.playbook and playbook_run.playbook.metadata:
                playbook_code = playbook_run.playbook.metadata.playbook_code
            elif playbook_run.playbook_json:
                playbook_code = playbook_run.playbook_json.playbook_code

        if not playbook_code:
            raise ValueError("Cannot determine playbook_code from PlaybookRun or context")

        workflow_step = WorkflowStep(
            playbook_code=playbook_code,
            kind=kind,
            inputs=inputs,
            input_mapping={},
            interaction_mode=interaction_modes
        )

        # Create HandoffPlan with single step (the playbook itself)
        handoff_plan = HandoffPlan(
            steps=[workflow_step],
            context=inputs
        )

        return handoff_plan
