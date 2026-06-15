import pytest

from backend.app.models.run_harness import (
    RunHarnessCapabilitySnapshotRef,
    RunHarnessKind,
    RunHarnessPermissionProfileRef,
    RunHarnessPolicyBundleRef,
    RunHarnessStatus,
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


class FakeExecutor:
    def __init__(self) -> None:
        self.calls = []
        self.snapshots = []

    async def resolve_tool_metadata_snapshot(self, tool_ref):
        self.snapshots.append(tool_ref)
        return {
            "tool_name": "cap_tool",
            "source_type": "capability",
            "provider": "cap",
            "danger_level": "low",
            "version": "1.0.0",
        }

    async def execute_tool(self, tool_name, arguments, timeout=30.0):
        self.calls.append((tool_name, arguments, timeout))
        return ToolExecutionResult(
            success=True,
            tool_name=tool_name,
            tool_type="builtin",
            result={"artifact_refs": ["artifact-1"], "payload": "ignored"},
            execution_time=0.12,
            metadata={"tool_source": "capability"},
        )


def _envelope(
    *,
    workspace_id: str = "ws",
    side_effect: SideEffectClass = SideEffectClass.READONLY,
) -> RunIntentEnvelope:
    return RunIntentEnvelope(
        decision_id="decision-1",
        workspace_id=workspace_id,
        profile_id="profile-1",
        origin_surface=RunIntentSource.TOOL_RAIL,
        intent_text="run deterministic tool",
        capability_snapshot_ref=RunHarnessCapabilitySnapshotRef(
            ref="capability-snapshot-1",
            capability_codes=["cap"],
        ),
        permission_profile_ref=RunHarnessPermissionProfileRef(ref="permission-1"),
        policy_bundle_ref=RunHarnessPolicyBundleRef(ref="policy-bundle-1"),
        requested_side_effects=[side_effect],
        idempotency_key="idem-1",
        trace_id="trace-1",
    )


def _request(
    *,
    side_effect: SideEffectClass = SideEffectClass.READONLY,
) -> RunHarnessToolExecutionRequest:
    return RunHarnessToolExecutionRequest(
        run_id="run-1",
        episode_id="episode-1",
        envelope=_envelope(side_effect=side_effect),
        tool_ref="cap.tool",
        arguments={"value": 1},
        side_effect=side_effect,
        policy=ToolAdmissionPolicy(
            policy_ref="policy-1",
            allowed_tool_refs=["cap.tool"],
            allowed_side_effects=[side_effect],
        ),
    )


@pytest.mark.asyncio
async def test_tool_execution_service_runs_single_production_path() -> None:
    ledger = MemoryEpisodeLedger()
    executor = FakeExecutor()
    service = RunHarnessToolExecutionService(
        episode_ledger=ledger,
        executor=executor,
    )

    result = await service.execute(_request())

    assert result.status == RunHarnessStatus.SUCCEEDED
    assert result.harness_kind == RunHarnessKind.DETERMINISTIC_TOOL
    assert result.output_artifact_refs == ["artifact-1"]
    assert set(result.metadata.keys()) == {
        "tool_name",
        "tool_type",
        "execution_time",
        "tool_source",
        "ledger_episode_id",
    }
    assert result.metadata["ledger_episode_id"] == "episode-1"
    assert executor.calls == [("cap.tool", {"value": 1}, 30.0)]
    assert executor.snapshots == ["cap.tool"]

    assert len(ledger.created) == 1
    _, selection_snapshot = ledger.created[0]
    assert selection_snapshot["run_id"] == "run-1"
    assert selection_snapshot["workspace_id"] == "ws"
    assert selection_snapshot["harness_kind"] == "deterministic_tool"
    assert selection_snapshot["tool_ref"] == "cap.tool"
    assert selection_snapshot["capability_snapshot_refs"][0]["ref"] == (
        "capability-snapshot-1"
    )

    assert [event["event_type"] for event in ledger.events] == [
        "tool_execution_requested",
        "tool_admission_evaluated",
        "tool_execution_started",
        "tool_execution_completed",
    ]
    started = ledger.events[2]["payload"]["metadata"]["tool_snapshot"]
    assert started == {
        "tool_name": "cap_tool",
        "source_type": "capability",
        "provider": "cap",
        "danger_level": "low",
        "version": "1.0.0",
    }
