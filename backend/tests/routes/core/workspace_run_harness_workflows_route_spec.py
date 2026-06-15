import importlib.util
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.models.run_harness import (
    RunHarnessCapabilitySnapshotRef,
    RunHarnessKind,
    RunHarnessPermissionProfileRef,
    RunHarnessPolicyBundleRef,
    RunHarnessResult,
    RunHarnessStatus,
    RunHarnessWaitKind,
    RunHarnessWaitState,
    RunIntentEnvelope,
    RunIntentSource,
)
from backend.app.models.run_harness_workflow_execution import (
    RunHarnessWorkflowExecutionRequest,
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
    "run_harness_workflows_route_under_test",
    _ROUTE_PATH,
)
assert _ROUTE_SPEC is not None and _ROUTE_SPEC.loader is not None
run_harness = importlib.util.module_from_spec(_ROUTE_SPEC)
_ROUTE_SPEC.loader.exec_module(run_harness)


class FakeWorkflowExecutionService:
    def __init__(self) -> None:
        self.requests = []

    async def start(self, request):
        self.requests.append(request)
        return RunHarnessResult(
            run_id=request.run_id,
            episode_id=request.episode_id,
            harness_kind=RunHarnessKind.DURABLE_WORKFLOW,
            status=RunHarnessStatus.WAITING,
            wait_state=RunHarnessWaitState(
                kind=RunHarnessWaitKind.RESOURCE,
                reason="workflow_execution_running",
            ),
            metadata={"ledger_episode_id": request.episode_id},
        )


def _request(workspace_id: str = "ws") -> RunHarnessWorkflowExecutionRequest:
    envelope = RunIntentEnvelope(
        decision_id="decision-1",
        workspace_id=workspace_id,
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
        workspace_id=workspace_id,
        project_id="project-1",
        profile_id="profile-1",
    )


def _build_client(service: FakeWorkflowExecutionService) -> TestClient:
    app = FastAPI()
    app.include_router(run_harness.router, prefix="/api/v1/workspaces")
    app.dependency_overrides[run_harness.get_workspace] = lambda: Workspace(
        id="ws",
        title="Workspace",
        owner_user_id="user",
    )
    app.dependency_overrides[run_harness.get_store] = lambda: object()
    app.dependency_overrides[run_harness.get_workflow_execution_service] = (
        lambda: service
    )
    return TestClient(app)


def test_workspace_run_harness_workflow_route_calls_service_only() -> None:
    service = FakeWorkflowExecutionService()
    client = _build_client(service)

    response = client.post(
        "/api/v1/workspaces/ws/run-harness/workflows/start",
        json=_request().model_dump(mode="json"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "waiting"
    assert payload["wait_state"]["reason"] == "workflow_execution_running"
    assert len(service.requests) == 1
    assert service.requests[0].playbook_code == "workflow_playbook"


def test_workspace_run_harness_workflow_route_enforces_workspace_scope() -> None:
    service = FakeWorkflowExecutionService()
    client = _build_client(service)

    response = client.post(
        "/api/v1/workspaces/ws/run-harness/workflows/start",
        json=_request(workspace_id="other-ws").model_dump(mode="json"),
    )

    assert response.status_code == 422
    assert service.requests == []
