from backend.app.models.run_harness import RunHarnessWaitKind
from backend.app.services.run_harness.workflow_ledger_bridge import (
    RunHarnessWorkflowLedgerBridge,
)


class MemoryEpisodeLedger:
    def __init__(self) -> None:
        self.result = None

    def append_event(self, episode_id, event_type, status, payload):
        return 1

    def upsert_result(self, result):
        self.result = result
        return result


def test_user_reserved_checkpoint_maps_to_human_approval_wait() -> None:
    bridge = RunHarnessWorkflowLedgerBridge(MemoryEpisodeLedger())

    result = bridge.record_pending(
        "episode-1",
        "execution-1",
        {
            "pause_mode": "user_reserved",
            "resume_token": "resume-1",
            "checkpoint_ref": "checkpoint-1",
        },
        None,
    )

    assert result.wait_state is not None
    assert result.wait_state.kind == RunHarnessWaitKind.HUMAN_APPROVAL
    assert result.wait_state.resume_token == "resume-1"


def test_non_human_checkpoint_maps_to_resource_wait() -> None:
    bridge = RunHarnessWorkflowLedgerBridge(MemoryEpisodeLedger())

    result = bridge.record_pending(
        "episode-1",
        "execution-1",
        {"step_id": "step-1", "error_type": "remote_unavailable"},
        "temporary wait",
    )

    assert result.wait_state is not None
    assert result.wait_state.kind == RunHarnessWaitKind.RESOURCE
    assert result.wait_state.reason == "workflow_checkpoint_wait"
