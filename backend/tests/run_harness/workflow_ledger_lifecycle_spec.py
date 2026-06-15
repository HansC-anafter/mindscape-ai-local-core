from types import SimpleNamespace

from backend.app.models.run_harness import RunHarnessStatus
from backend.app.services.run_harness.workflow_ledger_bridge import (
    RunHarnessWorkflowLedgerBridge,
)


class MemoryEpisodeLedger:
    def __init__(self) -> None:
        self.events = []
        self.results = []

    def append_event(self, episode_id, event_type, status, payload):
        self.events.append(
            {
                "episode_id": episode_id,
                "event_type": event_type,
                "status": status,
                "payload": payload,
            }
        )
        return len(self.events)

    def upsert_result(self, result):
        self.results.append(result)
        return result


def test_workflow_ledger_bridge_records_lifecycle_sequence() -> None:
    ledger = MemoryEpisodeLedger()
    bridge = RunHarnessWorkflowLedgerBridge(ledger)

    bridge.record_started(
        "episode-1",
        "execution-1",
        {"playbook_code": "workflow_playbook"},
    )
    pending = bridge.record_pending(
        "episode-1",
        "execution-1",
        {"step_id": "step-1", "error_type": "remote_wait"},
        "temporary wait",
    )
    terminal = bridge.record_terminal(
        "episode-1",
        "execution-1",
        SimpleNamespace(
            status="completed",
            outputs={"artifact_refs": ["artifact-1"]},
            checkpoint=None,
            error=None,
        ),
        {"status": "completed"},
    )
    failed = bridge.record_failed("episode-1", "execution-1", "boom")

    assert pending.status == RunHarnessStatus.WAITING
    assert terminal.status == RunHarnessStatus.SUCCEEDED
    assert terminal.output_artifact_refs == ["artifact-1"]
    assert failed.status == RunHarnessStatus.FAILED
    assert [event["event_type"] for event in ledger.events] == [
        "workflow_execution_started",
        "workflow_execution_pending",
        "workflow_execution_completed",
        "workflow_execution_failed",
    ]
    assert [result.status for result in ledger.results] == [
        RunHarnessStatus.WAITING,
        RunHarnessStatus.SUCCEEDED,
        RunHarnessStatus.FAILED,
    ]


def test_workflow_ledger_bridge_maps_completed_step_errors_to_failure() -> None:
    ledger = MemoryEpisodeLedger()
    bridge = RunHarnessWorkflowLedgerBridge(ledger)

    result = bridge.record_terminal(
        "episode-1",
        "execution-1",
        SimpleNamespace(
            status="completed",
            outputs={},
            checkpoint=None,
            error=None,
        ),
        {"status": "completed", "workflow_failed": True},
    )

    assert result.status == RunHarnessStatus.FAILED
    assert result.failure is not None
    assert result.failure.message == "Workflow completed with step errors"
