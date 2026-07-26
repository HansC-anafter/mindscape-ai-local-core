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
from backend.app.services.unified_tool_executor import UnifiedToolExecutor
from backend.app.services.unified_tool_executor_core.governance_context import (
    VerifiedToolExecutionContext,
)
from backend.app.services.tools.registry import register_reporting_tools


class _Ledger:
    def __init__(self):
        self.events = []

    def get_terminal_result(self, episode_id):
        return None

    def get_observation(self, episode_id):
        return None

    def create_episode(self, episode, snapshot):
        return episode

    def append_event(self, episode_id, event_type, status, payload):
        self.events.append(event_type)
        return len(self.events)

    def upsert_result(self, result):
        return result


class _Executor:
    def __init__(self):
        self.context = None

    async def resolve_tool_metadata_snapshot(self, tool_ref):
        return {
            "tool_name": tool_ref,
            "source_type": "builtin",
            "provider": "core",
            "danger_level": "medium",
            "version": "1.0.0",
        }

    async def execute_tool(
        self,
        tool_name,
        arguments,
        timeout=30.0,
        *,
        governance_context=None,
    ):
        self.context = governance_context
        return ToolExecutionResult(
            success=True,
            tool_name=tool_name,
            tool_type="builtin",
            result={"artifact_refs": ["report-bundle-a"]},
        )


def _request():
    return RunHarnessToolExecutionRequest(
        run_id="run-a",
        episode_id="episode-a",
        envelope=RunIntentEnvelope(
            decision_id="decision-a",
            workspace_id="workspace-a",
            profile_id="owner-a",
            origin_surface=RunIntentSource.TOOL_RAIL,
            intent_text="package report",
            capability_snapshot_ref=RunHarnessCapabilitySnapshotRef(
                ref="snapshot-a"
            ),
            permission_profile_ref=RunHarnessPermissionProfileRef(
                ref="permission-a"
            ),
            policy_bundle_ref=RunHarnessPolicyBundleRef(
                ref="policy-a"
            ),
            requested_side_effects=[SideEffectClass.READONLY],
            idempotency_key="idem-a",
            trace_id="trace-a",
        ),
        tool_ref="core.workspace_package_report",
        arguments={
            "workspace_id": "workspace-a",
            "report_path": "reports/html/report.html",
        },
        side_effect=SideEffectClass.READONLY,
        policy=ToolAdmissionPolicy(
            policy_ref="policy-a",
            allowed_tool_refs=["core.workspace_package_report"],
            allowed_side_effects=[SideEffectClass.READONLY],
        ),
    )


def _context():
    selector = "core.workspace_package_report"
    return VerifiedToolExecutionContext(
        snapshot_hash="1" * 64,
        workspace_id="workspace-a",
        actor_user_id="owner-a",
        allowed_workspace_ids=("workspace-a",),
        allowed_group_ids=(),
        workspace_owner_user_id="owner-a",
        active_group_id=None,
        group_owner_user_id=None,
        root_execution_id="run-a",
        trace_id="trace-a",
        source_entry="local",
        selector_lineage=(selector,),
        context_sha256="2" * 64,
    )


@pytest.mark.asyncio
async def test_run_harness_passes_only_derived_controller_context():
    executor = _Executor()
    service = RunHarnessToolExecutionService(
        episode_ledger=_Ledger(),
        executor=executor,
    )
    result = await service.execute(
        _request(),
        governance_context=_context(),
    )

    assert result.status == RunHarnessStatus.SUCCEEDED
    assert executor.context.selector_lineage == (
        "core.workspace_package_report",
        "core.workspace_package_report",
    )


@pytest.mark.asyncio
async def test_run_harness_executes_canonical_report_tool(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    sandbox = (
        tmp_path / "workspaces" / "workspace-a" / "sandbox"
    )
    report = sandbox / "reports" / "html" / "report.html"
    report.parent.mkdir(parents=True)
    report.write_text(
        "<!doctype html><p>Run harness report</p>",
        encoding="utf-8",
    )
    register_reporting_tools()
    request = _request().model_copy(
        update={
            "arguments": {
                "workspace_id": "workspace-a",
                "report_path": (
                    report.relative_to(sandbox).as_posix()
                ),
            },
            "side_effect": SideEffectClass.SOFT_WRITE,
            "approval_granted": True,
            "policy": ToolAdmissionPolicy(
                policy_ref="policy-a",
                allowed_tool_refs=[
                    "core.workspace_package_report"
                ],
                allowed_side_effects=[
                    SideEffectClass.SOFT_WRITE
                ],
            ),
        }
    )
    service = RunHarnessToolExecutionService(
        episode_ledger=_Ledger(),
        executor=UnifiedToolExecutor(),
    )

    result = await service.execute(
        request,
        governance_context=_context(),
    )

    assert result.status == RunHarnessStatus.SUCCEEDED
    assert result.output_artifact_refs == []
