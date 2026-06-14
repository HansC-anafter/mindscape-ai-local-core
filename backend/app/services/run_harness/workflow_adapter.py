"""Adapter from the existing runtime port result to run harness result."""

from backend.app.core.runtime_port import ExecutionResult
from backend.app.models.run_harness import (
    RunHarnessFailure,
    RunHarnessKind,
    RunHarnessResult,
    RunHarnessStatus,
    RunHarnessWaitKind,
    RunHarnessWaitState,
)


class DurableWorkflowHarnessAdapter:
    def map_result(self, result: ExecutionResult, *, episode_id: str) -> RunHarnessResult:
        if result.status in {"paused", "waiting"}:
            return RunHarnessResult(
                run_id=result.execution_id,
                episode_id=episode_id,
                harness_kind=RunHarnessKind.DURABLE_WORKFLOW,
                status=RunHarnessStatus.WAITING,
                wait_state=RunHarnessWaitState(
                    kind=RunHarnessWaitKind.HUMAN_APPROVAL,
                    reason="Workflow runtime paused at a resumable checkpoint.",
                    resume_token=(result.checkpoint or {}).get("resume_token"),
                ),
                metadata={"checkpoint_available": result.checkpoint is not None},
            )
        if result.status == "failed":
            return RunHarnessResult(
                run_id=result.execution_id,
                episode_id=episode_id,
                harness_kind=RunHarnessKind.DURABLE_WORKFLOW,
                status=RunHarnessStatus.FAILED,
                failure=RunHarnessFailure(
                    code="workflow_execution_failed",
                    message=result.error or "Workflow execution failed.",
                    retryable=result.checkpoint is not None,
                ),
            )
        mapped_status = (
            RunHarnessStatus.RUNNING
            if result.status == "running"
            else RunHarnessStatus.SUCCEEDED
        )
        return RunHarnessResult(
            run_id=result.execution_id,
            episode_id=episode_id,
            harness_kind=RunHarnessKind.DURABLE_WORKFLOW,
            status=mapped_status,
            output_artifact_refs=[
                str(item) for item in result.outputs.get("artifact_refs", [])
            ],
            metadata={"checkpoint_available": result.checkpoint is not None},
        )

