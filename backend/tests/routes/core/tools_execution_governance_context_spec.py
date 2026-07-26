from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.dependencies.auth import AuthContext, get_current_user
from backend.app.routes.core.tools import execution
from backend.app.services.unified_tool_executor import ToolExecutionResult
from backend.app.services.unified_tool_executor import UnifiedToolExecutor
from backend.app.services.tools.registry import register_reporting_tools
from backend.app.services.workspace_capability_admission.contracts import (
    AdmissionDenied,
    RootAdmissionResult,
    RootPrincipalEvidence,
)
from backend.app.services.workspace_capability_admission.execution_snapshot import (
    build_execution_snapshot,
)


def _admission():
    snapshot = build_execution_snapshot(
        {
            "source_runtime_id": "runtime-a",
            "workspace_id": "workspace-a",
            "active_group_id": None,
            "topology_revision": None,
            "topology_snapshot_id": None,
            "topology_snapshot_hash": None,
            "wpcs_hash": "1" * 64,
            "catalog_hash": "2" * 64,
            "admission_mode": "legacy_unmanaged",
            "pcs_id": None,
            "pcs_version": None,
            "product_surface_id": "mcp-gateway",
            "selector_kind": "tool",
            "selector_key": "core.workspace_package_report",
            "operation_type": "modify",
            "entry": "local",
            "execution_backend": "local",
            "deployment_mode": "unmanaged_local",
            "deployment_state_revision": 0,
            "deployment_envelope_revision": None,
            "dce_hash": None,
            "availability": "not_configured",
            "diagnostics": [],
            "external_decision_id": None,
            "external_decision_issuer": None,
            "external_decision_expires_at": None,
            "provider_token_id": None,
            "trace_id": "trace-a",
            "root_execution_id": "root-a",
            "admitted_at": datetime(
                2026,
                7,
                27,
                tzinfo=timezone.utc,
            ),
        }
    )
    return RootAdmissionResult(
        snapshot=snapshot,
        principal_evidence=RootPrincipalEvidence(
            workspace_id="workspace-a",
            actor_user_id="owner-a",
            allowed_workspace_ids=("workspace-a",),
            allowed_group_ids=(),
            workspace_owner_user_id="owner-a",
            group_owner_user_id=None,
        ),
    )


class _AdmissionFacade:
    def __init__(self, *, deny=False):
        self.deny = deny

    async def admit_root(self, request):
        if self.deny:
            raise AdmissionDenied("capability_not_permitted")
        assert request.actor_user_id == "owner-a"
        return _admission()


class _Executor:
    def __init__(self):
        self.calls = []

    async def execute_tool(
        self,
        tool_name,
        arguments,
        timeout,
        *,
        governance_context,
    ):
        self.calls.append(
            (tool_name, arguments, governance_context)
        )
        return ToolExecutionResult(
            success=True,
            tool_name=tool_name,
            tool_type="builtin",
            result={"status": "completed"},
        )


def _client(executor):
    app = FastAPI()
    app.include_router(execution.router)
    app.dependency_overrides[execution.get_tool_executor] = (
        lambda: executor
    )
    app.dependency_overrides[get_current_user] = lambda: AuthContext(
        user_id="owner-a",
        tenant_id="local",
        workspace_ids=["workspace-a"],
    )
    return TestClient(app)


def _payload(workspace_id="workspace-a"):
    return {
        "workspace_id": workspace_id,
        "product_surface_id": "mcp-gateway",
        "operation_type": "modify",
        "tool_name": "core.workspace_package_report",
        "arguments": {
            "workspace_id": workspace_id,
            "report_path": "reports/html/report.html",
            "workspace_owner_user_id": "attacker",
        },
        "root_execution_id": "root-a",
        "trace_id": "trace-a",
    }


def test_tool_route_builds_context_from_root_admission(monkeypatch):
    executor = _Executor()
    monkeypatch.setattr(
        execution,
        "admission_facade",
        _AdmissionFacade(),
    )

    with _client(executor) as client:
        response = client.post(
            "/api/v1/tools/execute?profile_id=owner-a",
            json=_payload(),
        )

    assert response.status_code == 200
    assert len(executor.calls) == 1
    context = executor.calls[0][2]
    assert context.actor_user_id == "owner-a"
    assert context.workspace_owner_user_id == "owner-a"
    assert context.selector_lineage == (
        "core.workspace_package_report",
    )


def test_tool_route_denies_before_executor(monkeypatch):
    executor = _Executor()
    monkeypatch.setattr(
        execution,
        "admission_facade",
        _AdmissionFacade(deny=True),
    )

    with _client(executor) as client:
        response = client.post(
            "/api/v1/tools/execute?profile_id=owner-a",
            json=_payload("workspace-foreign"),
        )

    assert response.status_code == 403
    assert executor.calls == []


def test_tool_route_executes_the_canonical_report_bundle_path(
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
        "<!doctype html><p>Internal report</p>",
        encoding="utf-8",
    )
    register_reporting_tools()
    monkeypatch.setattr(
        execution,
        "admission_facade",
        _AdmissionFacade(),
    )

    with _client(UnifiedToolExecutor()) as client:
        response = client.post(
            "/api/v1/tools/execute?profile_id=owner-a",
            json={
                **_payload(),
                "arguments": {
                    "workspace_id": "workspace-a",
                    "report_path": (
                        report.relative_to(sandbox).as_posix()
                    ),
                },
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["result"]["status"] == "completed"
    assert payload["result"]["share_authorization"] == (
        "workspace_only"
    )
