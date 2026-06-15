import pytest

from backend.app.models.run_harness import (
    RunHarnessAttempt,
    RunHarnessCapabilitySnapshotRef,
    RunHarnessEpisode,
    RunHarnessKind,
    RunHarnessObservation,
    RunHarnessPermissionProfileRef,
    RunHarnessPolicyBundleRef,
    RunHarnessResult,
    RunHarnessStatus,
    RunHarnessStepEvent,
    RunHarnessWaitKind,
    RunIntentEnvelope,
    RunIntentSource,
    SideEffectClass,
    ToolAdmissionPolicy,
)
from backend.app.models.run_harness_tool_execution import (
    RunHarnessToolExecutionRequest,
)
from backend.app.services.run_harness.tool_execution_service import (
    RunHarnessToolExecutionService,
)
from backend.app.services.unified_tool_executor import ToolExecutionResult


class MemoryEpisodeLedger:
    def __init__(self) -> None:
        self.events = []
        self.result = None
        self.terminal_result = None
        self.observation = None

    def create_episode(self, episode, selection_snapshot):
        return episode

    def append_event(self, episode_id, event_type, status, payload):
        self.events.append(event_type)
        return len(self.events)

    def upsert_result(self, result):
        self.result = result
        return result

    def get_observation(self, episode_id):
        return self.observation

    def get_terminal_result(self, episode_id):
        return self.terminal_result


class FakeExecutor:
    def __init__(self) -> None:
        self.calls = []

    async def resolve_tool_metadata_snapshot(self, tool_ref):
        return {
            "tool_name": "cap_tool",
            "source_type": "capability",
            "provider": "cap",
            "danger_level": "low",
            "version": "1.0.0",
        }

    async def execute_tool(self, tool_name, arguments, timeout=30.0):
        self.calls.append(tool_name)
        return ToolExecutionResult(
            success=True,
            tool_name=tool_name,
            tool_type="builtin",
            result={"artifact_refs": ["artifact-1"]},
        )


def _request() -> RunHarnessToolExecutionRequest:
    envelope = RunIntentEnvelope(
        decision_id="decision-1",
        workspace_id="ws",
        profile_id="profile-1",
        origin_surface=RunIntentSource.TOOL_RAIL,
        intent_text="run deterministic tool",
        capability_snapshot_ref=RunHarnessCapabilitySnapshotRef(ref="cap-1"),
        permission_profile_ref=RunHarnessPermissionProfileRef(ref="permission-1"),
        policy_bundle_ref=RunHarnessPolicyBundleRef(ref="policy-bundle-1"),
        requested_side_effects=[SideEffectClass.READONLY],
        idempotency_key="idem-1",
        trace_id="trace-1",
    )
    return RunHarnessToolExecutionRequest(
        run_id="run-1",
        episode_id="episode-1",
        envelope=envelope,
        tool_ref="cap.tool",
        side_effect=SideEffectClass.READONLY,
        policy=ToolAdmissionPolicy(
            policy_ref="policy-1",
            allowed_tool_refs=["cap.tool"],
        ),
    )


@pytest.mark.asyncio
async def test_tool_execution_replays_terminal_result_without_reexecution() -> None:
    ledger = MemoryEpisodeLedger()
    executor = FakeExecutor()
    ledger.terminal_result = RunHarnessResult(
        run_id="run-1",
        episode_id="episode-1",
        harness_kind=RunHarnessKind.DETERMINISTIC_TOOL,
        status=RunHarnessStatus.SUCCEEDED,
        output_artifact_refs=["artifact-stored"],
    )
    service = RunHarnessToolExecutionService(
        episode_ledger=ledger,
        executor=executor,
    )

    result = await service.execute(_request())

    assert result.output_artifact_refs == ["artifact-stored"]
    assert result.status == RunHarnessStatus.SUCCEEDED
    assert executor.calls == []
    assert ledger.events == []


@pytest.mark.asyncio
async def test_tool_execution_duplicate_running_episode_waits_without_reexecution() -> None:
    ledger = MemoryEpisodeLedger()
    executor = FakeExecutor()
    ledger.observation = RunHarnessObservation(
        workspace_id="ws",
        episode=RunHarnessEpisode(
            episode_id="episode-1",
            intent_envelope_ref="intent-1",
            selection_ref="selection-1",
            status=RunHarnessStatus.RUNNING,
            attempts=[
                RunHarnessAttempt(
                    attempt_id="attempt-1",
                    attempt_number=1,
                    status=RunHarnessStatus.RUNNING,
                    step_events=[
                        RunHarnessStepEvent(
                            event_id="event-1",
                            event_type="tool_execution_started",
                            status=RunHarnessStatus.RUNNING,
                        )
                    ],
                )
            ],
        ),
        result=RunHarnessResult(
            run_id="run-1",
            episode_id="episode-1",
            harness_kind=RunHarnessKind.DETERMINISTIC_TOOL,
            status=RunHarnessStatus.RUNNING,
        ),
    )
    service = RunHarnessToolExecutionService(
        episode_ledger=ledger,
        executor=executor,
    )

    result = await service.execute(_request())

    assert result.status == RunHarnessStatus.WAITING
    assert result.wait_state is not None
    assert result.wait_state.kind == RunHarnessWaitKind.RESOURCE
    assert result.wait_state.reason == "tool_execution_already_in_progress"
    assert executor.calls == []
    assert ledger.events == []
