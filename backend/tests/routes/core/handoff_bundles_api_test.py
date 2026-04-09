from pathlib import Path
import asyncio
import importlib.util
import sys
import types
from types import SimpleNamespace

import httpx
from fastapi import FastAPI

from backend.app.models.handoff import DeliverableSpec, HandoffIn
from backend.app.services.handoff_bundle_service import HandoffBundleService


SIGNING_KEY_FIXTURE = "fixture-route-signing-key-32!"


def _load_handoff_bundles_module():
    fake_store_package = types.ModuleType("backend.app.services.stores")
    fake_store_package.__path__ = []
    fake_compile_job_store_module = types.ModuleType(
        "backend.app.services.stores.compile_job_store"
    )
    fake_compile_job_store_module.CompileJobStore = object
    sys.modules.setdefault("backend.app.services.stores", fake_store_package)
    sys.modules.setdefault(
        "backend.app.services.stores.compile_job_store",
        fake_compile_job_store_module,
    )

    module_path = (
        Path(__file__).resolve().parents[3]
        / "app"
        / "routes"
        / "core"
        / "handoff_bundles.py"
    )
    spec = importlib.util.spec_from_file_location(
        "handoff_bundles_route_test_module",
        module_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ASGIAsyncTestClient:
    def __init__(self, app):
        self.app = app
        self.base_url = "http://testserver"

    def request(self, method, url, **kwargs):
        async def _request():
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url=self.base_url,
            ) as client:
                return await client.request(method, url, **kwargs)

        return asyncio.run(_request())

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)


def _make_compile_request(*, secret_key: str):
    handoff = HandoffIn(
        handoff_id="handoff-route-001",
        workspace_id="ws-route-001",
        intent_summary="Compile this handoff",
        goals=["ship", "verify"],
        deliverables=[
            DeliverableSpec(name="summary.md", mime_type="text/markdown"),
        ],
    )
    bundle = HandoffBundleService().package_handoff(
        handoff_in=handoff,
        source_device_id="device-route-A",
        secret_key=SIGNING_KEY_FIXTURE,
    )
    return {
        "bundle": bundle.model_dump(mode="json"),
        "workspace_id": "ws-route-001",
        "project_id": "proj-route-001",
        "profile_id": "profile-route-001",
        "thread_id": "thread-route-001",
        "secret_key": secret_key,
    }


def test_compile_route_rejects_unverified_bundle_before_workspace_lookup(monkeypatch):
    module = _load_handoff_bundles_module()

    class ExplodingWorkspaceStore:
        def __init__(self):
            raise AssertionError("workspace lookup should not run for invalid bundle")

    fake_ws_module = types.ModuleType(
        "backend.app.services.stores.postgres.workspaces_store"
    )
    fake_ws_module.PostgresWorkspacesStore = ExplodingWorkspaceStore
    monkeypatch.setitem(
        sys.modules,
        "backend.app.services.stores.postgres.workspaces_store",
        fake_ws_module,
    )

    app = FastAPI()
    app.include_router(module.router)
    client = ASGIAsyncTestClient(app)

    response = client.post(
        "/api/handoff-bundles/compile",
        json=_make_compile_request(secret_key="wrong-signing-key"),
    )

    assert response.status_code == 403
    assert "verification failed" in response.json()["detail"]


def test_get_compile_job_redacts_internal_metadata(monkeypatch):
    module = _load_handoff_bundles_module()
    job = module.CompileJob.new(
        workspace_id="ws-route-001",
        project_id="proj-route-001",
        thread_id="thread-route-001",
        profile_id="profile-route-001",
        session_id="sess-route-001",
        metadata={
            "entry_point": "compile",
            "_internal_recovery_context": {"handoff_in": {"handoff_id": "hidden"}},
        },
    )

    class FakeCompileJobStore:
        def get_by_id(self, job_id):
            return job if job_id == job.id else None

    monkeypatch.setattr(module, "CompileJobStore", lambda: FakeCompileJobStore())

    app = FastAPI()
    app.include_router(module.router)
    client = ASGIAsyncTestClient(app)

    response = client.get(f"/api/handoff-bundles/compile-jobs/{job.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == job.id
    assert payload["metadata"] == {"entry_point": "compile"}


def test_compile_route_accepts_verified_bundle_and_returns_ids(monkeypatch):
    module = _load_handoff_bundles_module()

    workspace_calls = []
    route_calls = []
    created_jobs = []
    dispatcher_notifications = []
    fake_session = SimpleNamespace(id="sess-route-001", metadata={})
    fake_workspace = SimpleNamespace(
        id="ws-route-001",
        runtime_profile=SimpleNamespace(name="default"),
    )

    class FakeWorkspaceStore:
        async def get_workspace(self, workspace_id):
            workspace_calls.append(workspace_id)
            return fake_workspace

    class FakeIngressRouter:
        async def decide(self, **kwargs):
            route_calls.append(kwargs)
            return SimpleNamespace(route_kind="meeting")

    class FakeCompileJobStore:
        def create(self, job):
            created_jobs.append(job)
            return job

    class FakeCompileJobDispatchManager:
        def notify_pending_job(self):
            dispatcher_notifications.append("notified")

    def fake_get_or_create_compile_session(**kwargs):
        return fake_session, False

    fake_ws_module = types.ModuleType(
        "backend.app.services.stores.postgres.workspaces_store"
    )
    fake_ws_module.PostgresWorkspacesStore = FakeWorkspaceStore
    fake_router_module = types.ModuleType(
        "backend.app.services.conversation.ingress_router"
    )
    fake_router_module.IngressRouter = FakeIngressRouter
    monkeypatch.setitem(
        sys.modules,
        "backend.app.services.stores.postgres.workspaces_store",
        fake_ws_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "backend.app.services.conversation.ingress_router",
        fake_router_module,
    )
    fake_dispatch_manager_module = types.ModuleType(
        "backend.app.services.compile_job_dispatch_manager"
    )
    fake_dispatch_manager_module.get_compile_job_dispatch_manager = (
        lambda: FakeCompileJobDispatchManager()
    )
    monkeypatch.setitem(
        sys.modules,
        "backend.app.services.compile_job_dispatch_manager",
        fake_dispatch_manager_module,
    )
    monkeypatch.setattr(module, "CompileJobStore", lambda: FakeCompileJobStore())
    monkeypatch.setattr(
        module.HandoffBundleService,
        "get_or_create_compile_session",
        staticmethod(fake_get_or_create_compile_session),
    )

    app = FastAPI()
    app.include_router(module.router)
    client = ASGIAsyncTestClient(app)

    response = client.post(
        "/api/handoff-bundles/compile",
        json=_make_compile_request(secret_key=SIGNING_KEY_FIXTURE),
    )

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"
    assert data["job_id"] == data["compile_job_id"]
    assert data["session_id"] == "sess-route-001"
    assert workspace_calls == ["ws-route-001"]
    assert route_calls == [
        {
            "execution_mode": "meeting",
            "meeting_enabled": True,
            "entry_point": "compile",
        }
    ]
    assert len(created_jobs) == 1
    assert created_jobs[0].session_id == "sess-route-001"
    assert created_jobs[0].metadata["entry_point"] == "compile"
    assert created_jobs[0].metadata["route_kind"] == "meeting"
    assert created_jobs[0].metadata["model_name"] is None
    assert created_jobs[0].metadata["active_session_reused"] is False
    recovery_context = created_jobs[0].metadata["_internal_recovery_context"]
    assert recovery_context["workspace_id"] == "ws-route-001"
    assert recovery_context["project_id"] == "proj-route-001"
    assert recovery_context["profile_id"] == "profile-route-001"
    assert recovery_context["thread_id"] == "thread-route-001"
    assert recovery_context["model_name"] is None
    assert recovery_context["source_device_id"] == "device-route-A"
    assert recovery_context["executor_target_client_id"] is None
    assert recovery_context["handoff_in"]["handoff_id"] == "handoff-route-001"
    assert recovery_context["handoff_in"]["workspace_id"] == "ws-route-001"
    assert recovery_context["handoff_in"]["intent_summary"] == "Compile this handoff"
    assert recovery_context["handoff_in"]["goals"] == ["ship", "verify"]
    assert len(recovery_context["handoff_in"]["deliverables"]) == 1
    assert recovery_context["handoff_in"]["deliverables"][0]["name"] == "summary.md"
    assert (
        recovery_context["handoff_in"]["deliverables"][0]["mime_type"]
        == "text/markdown"
    )
    assert dispatcher_notifications == ["notified"]
