from types import SimpleNamespace

import pytest

from backend.app.models.run_harness import (
    RunHarnessCapabilitySnapshotRef,
    RunHarnessKind,
    RunHarnessPermissionProfileRef,
    RunHarnessPolicyBundleRef,
    RunHarnessStatus,
    RunHarnessWaitKind,
    RunIntentEnvelope,
    RunIntentSource,
)
from backend.app.models.run_harness_workflow_execution import (
    RunHarnessWorkflowExecutionRequest,
)
from backend.app.services.run_harness.workflow_execution_service import (
    RunHarnessWorkflowExecutionService,
)
from backend.app.services.run_harness.workflow_ledger_bridge import (
    RUN_HARNESS_EPISODE_ID_KEY,
    RUN_HARNESS_RUN_ID_KEY,
    RUN_HARNESS_STARTED_RECORDED_KEY,
    RunHarnessWorkflowLedgerBridge,
)


class MemoryEpisodeLedger:
    def __init__(self) -> None:
        self.created = []
        self.events = []
        self.result = None
        self.terminal_result = None
        self.observation = None

    def create_episode(self, episode, selection_snapshot):
        self.created.append((episode, selection_snapshot))
        return episode

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
        self.result = result
        return result

    def get_observation(self, episode_id):
        return self.observation

    def get_terminal_result(self, episode_id):
        return self.terminal_result


def _request() -> RunHarnessWorkflowExecutionRequest:
    envelope = RunIntentEnvelope(
        decision_id="decision-1",
        workspace_id="ws",
        profile_id="profile-1",
        origin_surface=RunIntentSource.WORKFLOW,
        intent_text="start workflow",
        capability_snapshot_ref=RunHarnessCapabilitySnapshotRef(ref="cap-1"),
        permission_profile_ref=RunHarnessPermissionProfileRef(ref="permission-1"),
        policy_bundle_ref=RunHarnessPolicyBundleRef(ref="policy-bundle-1"),
        idempotency_key="idem-1",
        trace_id="trace-1",
    )
    return RunHarnessWorkflowExecutionRequest(
        run_id="execution-1",
        episode_id="episode-1",
        envelope=envelope,
        playbook_code="workflow_playbook",
        normalized_inputs={"input": "value"},
        workspace_id="ws",
        project_id="project-1",
        profile_id="profile-1",
        execution_backend="in_process",
    )


@pytest.mark.asyncio
async def test_workflow_execution_service_starts_existing_runtime_path() -> None:
    ledger = MemoryEpisodeLedger()
    captured_inputs = {}

    async def fake_starter(request, normalized_inputs):
        captured_inputs.update(normalized_inputs)
        return SimpleNamespace(execution_id="execution-1", status="running")

    service = RunHarnessWorkflowExecutionService(
        episode_ledger=ledger,
        bridge=RunHarnessWorkflowLedgerBridge(ledger),
        workflow_starter=fake_starter,
    )

    result = await service.start(_request())

    assert result.status == RunHarnessStatus.WAITING
    assert result.harness_kind == RunHarnessKind.DURABLE_WORKFLOW
    assert result.wait_state is not None
    assert result.wait_state.kind == RunHarnessWaitKind.RESOURCE
    assert result.wait_state.reason == "workflow_execution_running"
    assert captured_inputs["execution_id"] == "execution-1"
    assert captured_inputs[RUN_HARNESS_EPISODE_ID_KEY] == "episode-1"
    assert captured_inputs[RUN_HARNESS_RUN_ID_KEY] == "execution-1"
    assert captured_inputs[RUN_HARNESS_STARTED_RECORDED_KEY] is True

    assert len(ledger.created) == 1
    _episode, selection_snapshot = ledger.created[0]
    assert selection_snapshot["harness_kind"] == "durable_workflow"
    assert selection_snapshot["source_execution_id"] == "execution-1"
    assert [event["event_type"] for event in ledger.events] == [
        "workflow_execution_requested",
        "workflow_execution_started",
    ]
    assert ledger.result.status == RunHarnessStatus.WAITING


@pytest.mark.asyncio
async def test_workflow_execution_service_replays_terminal_result() -> None:
    ledger = MemoryEpisodeLedger()
    ledger.terminal_result = SimpleNamespace(
        status=RunHarnessStatus.SUCCEEDED,
        output_artifact_refs=["artifact-stored"],
    )
    starter_called = False

    async def fake_starter(_request, _normalized_inputs):
        nonlocal starter_called
        starter_called = True
        return SimpleNamespace(execution_id="execution-1", status="running")

    service = RunHarnessWorkflowExecutionService(
        episode_ledger=ledger,
        bridge=RunHarnessWorkflowLedgerBridge(ledger),
        workflow_starter=fake_starter,
    )

    result = await service.start(_request())

    assert result.output_artifact_refs == ["artifact-stored"]
    assert starter_called is False
    assert ledger.events == []
