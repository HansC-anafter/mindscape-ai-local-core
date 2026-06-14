from backend.app.core.runtime_port import ExecutionResult
from backend.app.models.run_harness import RunHarnessStatus
from backend.app.services.run_harness.workflow_adapter import (
    DurableWorkflowHarnessAdapter,
)


def test_workflow_adapter_maps_checkpoint_pause_to_wait_state() -> None:
    result = DurableWorkflowHarnessAdapter().map_result(
        ExecutionResult(
            status="paused",
            execution_id="execution-1",
            checkpoint={"resume_token": "resume-1"},
        ),
        episode_id="episode-1",
    )
    assert result.status == RunHarnessStatus.WAITING
    assert result.wait_state.resume_token == "resume-1"

