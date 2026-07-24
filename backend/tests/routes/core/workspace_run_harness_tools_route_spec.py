import importlib.util
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.dependencies.auth import AuthContext
from backend.app.models.run_harness import (
    RunHarnessCapabilitySnapshotRef,
    RunHarnessKind,
    RunHarnessPermissionProfileRef,
    RunHarnessPolicyBundleRef,
    RunHarnessResult,
    RunHarnessStatus,
    RunIntentEnvelope,
    RunIntentSource,
    SideEffectClass,
    ToolAdmissionPolicy,
)
from backend.app.models.run_harness_tool_execution import (
    RunHarnessToolExecutionRequest,
)
from backend.app.models.workspace import Workspace

_ROUTE_PATH = (
    Path(__file__).resolve().parents[3]
    / "app"
    / "routes"
    / "core"
    / "workspace"
    / "run_harness.py"
)
_ROUTE_SPEC = importlib.util.spec_from_file_location(
    "run_harness_tools_route_under_test",
    _ROUTE_PATH,
)
assert _ROUTE_SPEC is not None and _ROUTE_SPEC.loader is not None
run_harness = importlib.util.module_from_spec(_ROUTE_SPEC)
_ROUTE_SPEC.loader.exec_module(run_harness)


class FakeToolExecutionService:
    def __init__(self) -> None:
        self.requests = []

    async def execute(self, request):
        self.requests.append(request)
        return RunHarnessResult(
            run_id=request.run_id,
            episode_id=request.episode_id,
            harness_kind=RunHarnessKind.DETERMINISTIC_TOOL,
            status=RunHarnessStatus.SUCCEEDED,
            output_artifact_refs=["artifact-1"],
            metadata={"ledger_episode_id": request.episode_id},
        )


class FakeAdmissionFacade:
    async def admit_root(self, request):
        class Snapshot:
            schema_version = "mindscape.execution-admission-snapshot.v1"
            snapshot_hash = "a" * 64

            @staticmethod
            def model_dump(*, mode):
                assert mode == "json"
                return {
                    "schema_version": Snapshot.schema_version,
                    "snapshot_hash": Snapshot.snapshot_hash,
                    "workspace_id": request.workspace_id,
                    "root_execution_id": request.root_execution_id,
                }

        return type(
            "Admission",
            (),
            {"snapshot": Snapshot(), "external_decision": None},
        )()


def _request(workspace_id: str = "ws") -> RunHarnessToolExecutionRequest:
    envelope = RunIntentEnvelope(
        decision_id="decision-1",
        workspace_id=workspace_id,
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


def _build_client(service: FakeToolExecutionService) -> TestClient:
    app = FastAPI()
    app.include_router(run_harness.router, prefix="/api/v1/workspaces")
    app.dependency_overrides[run_harness.get_workspace] = lambda: Workspace(
        id="ws",
        title="Workspace",
        owner_user_id="user",
    )
    app.dependency_overrides[run_harness.get_store] = lambda: object()
    app.dependency_overrides[run_harness.get_tool_execution_service] = (
        lambda: service
    )
    app.dependency_overrides[run_harness.get_current_user] = lambda: AuthContext(
        user_id="user",
        tenant_id="local",
        workspace_ids=["ws"],
    )
    app.dependency_overrides[run_harness.get_product_admission_facade] = (
        lambda: FakeAdmissionFacade()
    )
    return TestClient(app)


def test_workspace_run_harness_tool_route_calls_service_only() -> None:
    service = FakeToolExecutionService()
    client = _build_client(service)

    response = client.post(
        "/api/v1/workspaces/ws/run-harness/tools/execute",
        json=_request().model_dump(mode="json"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "succeeded"
    assert payload["output_artifact_refs"] == ["artifact-1"]
    assert len(service.requests) == 1
    assert service.requests[0].tool_ref == "cap.tool"
    snapshot_ref = service.requests[0].envelope.capability_snapshot_ref
    assert snapshot_ref.digest == "a" * 64
    assert snapshot_ref.execution_admission_snapshot["workspace_id"] == "ws"


def test_workspace_run_harness_tool_route_enforces_workspace_scope() -> None:
    service = FakeToolExecutionService()
    client = _build_client(service)

    response = client.post(
        "/api/v1/workspaces/ws/run-harness/tools/execute",
        json=_request(workspace_id="other-ws").model_dump(mode="json"),
    )

    assert response.status_code == 422
    assert service.requests == []
