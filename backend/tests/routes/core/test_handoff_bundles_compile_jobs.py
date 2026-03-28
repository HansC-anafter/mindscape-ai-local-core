import json
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.app.models.handoff import HandoffIn
from backend.app.routes.core import handoff_bundles
from backend.app.services.handoff_bundle_service import HandoffBundleService


class _FakeCompileJobStore:
    def __init__(self):
        self.created = None
        self.failed = []
        self.jobs = {}

    def create(self, job):
        self.created = job
        self.jobs[job.id] = job
        return job

    def mark_failed(self, job_id, error):
        self.failed.append((job_id, error))
        return self.jobs[job_id]

    def get_by_id(self, job_id):
        return self.jobs.get(job_id)


@pytest.mark.asyncio
async def test_compile_route_returns_compile_job_id(monkeypatch):
    fake_store = _FakeCompileJobStore()
    fake_session = SimpleNamespace(id="sess_route_001")
    scheduled = {}

    async def _fake_compile_handoff_in(**kwargs):
        assert kwargs["compile_job_id"] == fake_store.created.id
        assert kwargs["compile_job_store"] is fake_store
        assert kwargs["session_override"] is fake_session
        assert kwargs["executor_target_client_id"] == "client-e2e-003"
        return {"status": "compiled"}

    def _fake_create_task(coro):
        scheduled["seen"] = True
        coro.close()
        return MagicMock()

    monkeypatch.setattr(
        handoff_bundles,
        "CompileJobStore",
        lambda: fake_store,
    )
    monkeypatch.setattr(
        HandoffBundleService,
        "get_or_create_compile_session",
        staticmethod(lambda **kwargs: (fake_session, False)),
    )
    monkeypatch.setattr(
        HandoffBundleService,
        "compile_handoff_in",
        staticmethod(_fake_compile_handoff_in),
    )
    monkeypatch.setattr(handoff_bundles.asyncio, "create_task", _fake_create_task)

    ws_store = MagicMock()
    ws_store.get_workspace = AsyncMock(
        return_value=SimpleNamespace(id="ws_route_001", runtime_profile=None)
    )
    ws_mod = types.ModuleType(
        "backend.app.services.stores.postgres.workspaces_store"
    )
    ws_mod.PostgresWorkspacesStore = MagicMock(return_value=ws_store)

    class _FakeIngressRouter:
        async def decide(self, **kwargs):
            return SimpleNamespace(route_kind="meeting")

    ingress_mod = types.ModuleType(
        "backend.app.services.conversation.ingress_router"
    )
    ingress_mod.IngressRouter = _FakeIngressRouter

    saved = {
        "backend.app.services.stores.postgres.workspaces_store": sys.modules.get(
            "backend.app.services.stores.postgres.workspaces_store"
        ),
        "backend.app.services.conversation.ingress_router": sys.modules.get(
            "backend.app.services.conversation.ingress_router"
        ),
    }
    sys.modules.update(
        {
            "backend.app.services.stores.postgres.workspaces_store": ws_mod,
            "backend.app.services.conversation.ingress_router": ingress_mod,
        }
    )
    try:
        svc = HandoffBundleService()
        bundle = svc.package_handoff(
            handoff_in=HandoffIn(
                handoff_id="h_route_001",
                workspace_id="ws_route_001",
                intent_summary="Compile route test",
                goals=["g1"],
            ),
            source_device_id="device_route_001",
            secret_key="route-fixture-signing-key",
        )

        request = handoff_bundles.CompileRequest(
            bundle=bundle.model_dump(mode="json"),
            workspace_id="ws_route_001",
            project_id="proj_route_001",
            profile_id="profile_route_001",
            thread_id="thread_route_001",
            secret_key="route-fixture-signing-key",
            executor_target_client_id="client-e2e-003",
        )
        result = await handoff_bundles.compile_bundle(request)
    finally:
        for key, value in saved.items():
            if value is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value

    payload = json.loads(result.body.decode("utf-8"))
    assert result.status_code == 202
    assert payload["compile_job_id"] == fake_store.created.id
    assert payload["status"] == "accepted"
    assert payload["session_id"] == "sess_route_001"
    assert fake_store.created.workspace_id == "ws_route_001"
    assert fake_store.created.project_id == "proj_route_001"
    assert fake_store.created.thread_id == "thread_route_001"
    assert fake_store.created.handoff_id == "h_route_001"
    assert fake_store.created.metadata["executor_target_client_id"] == "client-e2e-003"
    assert scheduled["seen"] is True


@pytest.mark.asyncio
async def test_get_compile_job_returns_serialized_job(monkeypatch):
    fake_store = _FakeCompileJobStore()
    job = handoff_bundles.CompileJob.new(
        workspace_id="ws_route_002",
        project_id="proj_route_002",
        thread_id="thread_route_002",
    )
    fake_store.create(job)
    monkeypatch.setattr(
        handoff_bundles,
        "CompileJobStore",
        lambda: fake_store,
    )

    result = await handoff_bundles.get_compile_job(job.id)

    assert result["id"] == job.id
    assert result["workspace_id"] == "ws_route_002"
    assert result["status"] == "accepted"
