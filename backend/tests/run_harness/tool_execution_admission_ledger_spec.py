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
        self.events.append(
            {
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
        return None

    def get_terminal_result(self, episode_id):
        return None


class FakeExecutor:
    def __init__(self) -> None:
        self.calls = []
        self.snapshot_calls = []

    async def resolve_tool_metadata_snapshot(self, tool_ref):
        self.snapshot_calls.append(tool_ref)
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


def _request(
    *,
    side_effect: SideEffectClass,
    policy: ToolAdmissionPolicy,
    approval_granted: bool = False,
    rollback_available: bool = False,
) -> RunHarnessToolExecutionRequest:
    envelope = RunIntentEnvelope(
        decision_id="decision-1",
        workspace_id="ws",
        profile_id="profile-1",
        origin_surface=RunIntentSource.TOOL_RAIL,
        intent_text="run deterministic tool",
        capability_snapshot_ref=RunHarnessCapabilitySnapshotRef(ref="cap-1"),
        permission_profile_ref=RunHarnessPermissionProfileRef(ref="permission-1"),
        policy_bundle_ref=RunHarnessPolicyBundleRef(ref="policy-bundle-1"),
        requested_side_effects=[side_effect],
        idempotency_key="idem-1",
        trace_id="trace-1",
    )
    return RunHarnessToolExecutionRequest(
        run_id="run-1",
        episode_id="episode-1",
        envelope=envelope,
        tool_ref="cap.tool",
        side_effect=side_effect,
        policy=policy,
        approval_granted=approval_granted,
        rollback_available=rollback_available,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_request", "expected_status", "expected_code"),
    [
        (
            _request(
                side_effect=SideEffectClass.SOFT_WRITE,
                policy=ToolAdmissionPolicy(
                    policy_ref="policy-wait",
                    allowed_tool_refs=["cap.tool"],
                    allowed_side_effects=[SideEffectClass.READONLY],
                    require_approval_for=[SideEffectClass.SOFT_WRITE],
                ),
            ),
            RunHarnessStatus.WAITING,
            None,
        ),
        (
            _request(
                side_effect=SideEffectClass.READONLY,
                policy=ToolAdmissionPolicy(
                    policy_ref="policy-deny",
                    denied_tool_refs=["cap.tool"],
                ),
            ),
            RunHarnessStatus.FAILED,
            "tool_admission_denied",
        ),
        (
            _request(
                side_effect=SideEffectClass.DESTRUCTIVE,
                policy=ToolAdmissionPolicy(
                    policy_ref="policy-escalate",
                    allowed_tool_refs=["cap.tool"],
                    allowed_side_effects=[SideEffectClass.DESTRUCTIVE],
                    require_approval_for=[],
                ),
            ),
            RunHarnessStatus.ESCALATED,
            None,
        ),
    ],
)
async def test_admission_blocks_non_allow_decisions_before_executor(
    tool_request,
    expected_status,
    expected_code,
) -> None:
    ledger = MemoryEpisodeLedger()
    executor = FakeExecutor()
    service = RunHarnessToolExecutionService(
        episode_ledger=ledger,
        executor=executor,
    )

    result = await service.execute(tool_request)

    assert result.status == expected_status
    assert (result.failure.code if result.failure else None) == expected_code
    assert executor.calls == []
    assert executor.snapshot_calls == []
    assert [event["event_type"] for event in ledger.events[:2]] == [
        "tool_execution_requested",
        "tool_admission_evaluated",
    ]


@pytest.mark.asyncio
async def test_allow_records_admission_before_started_event() -> None:
    ledger = MemoryEpisodeLedger()
    executor = FakeExecutor()
    service = RunHarnessToolExecutionService(
        episode_ledger=ledger,
        executor=executor,
    )

    result = await service.execute(
        _request(
            side_effect=SideEffectClass.READONLY,
            policy=ToolAdmissionPolicy(
                policy_ref="policy-allow",
                allowed_tool_refs=["cap.tool"],
            ),
        )
    )

    assert result.status == RunHarnessStatus.SUCCEEDED
    assert executor.calls == ["cap.tool"]
    event_types = [event["event_type"] for event in ledger.events]
    assert event_types.index("tool_admission_evaluated") < event_types.index(
        "tool_execution_started"
    )
    assert ledger.events[1]["payload"]["policy_eval"]["decision"] == "allow"
