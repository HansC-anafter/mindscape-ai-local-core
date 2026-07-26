import pytest

from backend.app.models.run_harness import (
    RunHarnessCapabilitySnapshotRef,
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
        self.events = []
        self.result = None

    def create_episode(self, episode, selection_snapshot):
        return episode

    def append_event(self, episode_id, event_type, status, payload):
        self.events.append(event_type)
        return len(self.events)

    def upsert_result(self, result):
        self.result = result
        return result

    def get_observation(self, episode_id):
        return None

    def get_terminal_result(self, episode_id):
        return None


class FakeExecutor:
    def __init__(self, *, snapshot=None, execution_result=None) -> None:
        self.calls = []
        self.snapshot = snapshot
        self.execution_result = execution_result

    async def resolve_tool_metadata_snapshot(self, tool_ref):
        return self.snapshot

    async def execute_tool(self, tool_name, arguments, timeout=30.0):
        self.calls.append(tool_name)
        return self.execution_result


def _snapshot():
    return {
        "tool_name": "cap_tool",
        "source_type": "capability",
        "provider": "cap",
        "danger_level": "low",
        "version": "1.0.0",
    }


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
async def test_mapping_reads_artifact_refs_from_result_then_metadata() -> None:
    ledger = MemoryEpisodeLedger()
    executor = FakeExecutor(
        snapshot=_snapshot(),
        execution_result=ToolExecutionResult(
            success=True,
            tool_name="cap.tool",
            tool_type="builtin",
            result={"artifact_refs": ["artifact-result"]},
            metadata={"artifact_refs": ["artifact-metadata"]},
        ),
    )
    service = RunHarnessToolExecutionService(
        episode_ledger=ledger,
        executor=executor,
    )

    result = await service.execute(_request())

    assert result.status == RunHarnessStatus.SUCCEEDED
    assert result.output_artifact_refs == ["artifact-result"]

    ledger = MemoryEpisodeLedger()
    executor = FakeExecutor(
        snapshot=_snapshot(),
        execution_result=ToolExecutionResult(
            success=True,
            tool_name="cap.tool",
            tool_type="builtin",
            result={"artifact_refs": "not-a-list"},
            metadata={"artifact_refs": ["artifact-metadata"]},
        ),
    )
    service = RunHarnessToolExecutionService(
        episode_ledger=ledger,
        executor=executor,
    )

    result = await service.execute(_request())

    assert result.status == RunHarnessStatus.SUCCEEDED
    assert result.output_artifact_refs == ["artifact-metadata"]


@pytest.mark.asyncio
async def test_mapping_converts_executor_failure_to_harness_failure() -> None:
    ledger = MemoryEpisodeLedger()
    executor = FakeExecutor(
        snapshot=_snapshot(),
        execution_result=ToolExecutionResult(
            success=False,
            tool_name="cap.tool",
            tool_type="builtin",
            error="boom",
            metadata={"artifact_refs": ["ignored"]},
        ),
    )
    service = RunHarnessToolExecutionService(
        episode_ledger=ledger,
        executor=executor,
    )

    result = await service.execute(_request())

    assert result.status == RunHarnessStatus.FAILED
    assert result.failure is not None
    assert result.failure.code == "tool_execution_failed"
    assert result.failure.message == "boom"
    assert result.output_artifact_refs == ["ignored"]


@pytest.mark.asyncio
async def test_mapping_preserves_disclosure_review_as_waiting() -> None:
    ledger = MemoryEpisodeLedger()
    executor = FakeExecutor(
        snapshot=_snapshot(),
        execution_result=ToolExecutionResult(
            success=True,
            tool_name="cap.tool",
            tool_type="builtin",
            result={
                "status": "preflight_completed",
                "artifact_created": False,
                "review_requirements": [
                    "verified_owner_review:report.html"
                ],
                "blocking_codes": [],
                "review_binding_sha256": "a" * 64,
            },
        ),
    )
    service = RunHarnessToolExecutionService(
        episode_ledger=ledger,
        executor=executor,
    )

    result = await service.execute(_request())

    assert result.status == RunHarnessStatus.WAITING
    assert result.wait_state.reason == (
        "artifact_disclosure_review_required"
    )
    assert result.metadata["review_binding_sha256"] == "a" * 64
    assert ledger.events[-1] == "tool_execution_waiting"


@pytest.mark.asyncio
async def test_missing_tool_metadata_snapshot_fails_closed_before_execution() -> None:
    ledger = MemoryEpisodeLedger()
    executor = FakeExecutor(
        snapshot=None,
        execution_result=ToolExecutionResult(
            success=True,
            tool_name="cap.tool",
            tool_type="builtin",
        ),
    )
    service = RunHarnessToolExecutionService(
        episode_ledger=ledger,
        executor=executor,
    )

    result = await service.execute(_request())

    assert result.status == RunHarnessStatus.FAILED
    assert result.failure is not None
    assert result.failure.code == "tool_metadata_snapshot_missing"
    assert executor.calls == []
