import inspect
from types import SimpleNamespace

import pytest

from backend.app.services import handoff_bundle_compile, handoff_bundle_recovery
from backend.app.services import handoff_bundle_service as service_module
from backend.app.services.handoff_bundle_service import HandoffBundleService


@pytest.mark.asyncio
async def test_compile_handoff_in_facade_delegates_to_helper(monkeypatch):
    captured = {}

    async def fake_compile_handoff_in(**kwargs):
        captured.update(kwargs)
        return {"status": "compiled", "session_id": "session-1"}

    monkeypatch.setattr(service_module, "_compile_handoff_in", fake_compile_handoff_in)

    handoff = SimpleNamespace(workspace_id="ws-1")
    result = await HandoffBundleService.compile_handoff_in(
        handoff_in=handoff,
        workspace=SimpleNamespace(id="ws-1", resolved_executor_runtime="codex_cli"),
        runtime_profile=SimpleNamespace(id="runtime-1"),
        profile_id="profile-1",
        thread_id="thread-1",
        project_id="project-1",
        model_name="model-1",
        source_device_id="device-1",
        route_decision=SimpleNamespace(route_kind="local"),
    )

    assert result == {"status": "compiled", "session_id": "session-1"}
    assert captured["handoff_in"] is handoff
    assert captured["workspace"].id == "ws-1"
    assert captured["runtime_profile"].id == "runtime-1"
    assert captured["profile_id"] == "profile-1"
    assert captured["thread_id"] == "thread-1"
    assert captured["project_id"] == "project-1"
    assert captured["model_name"] == "model-1"
    assert captured["source_device_id"] == "device-1"
    assert captured["route_decision"].route_kind == "local"


def test_recovery_helpers_remain_import_compatible_from_facade():
    assert (
        service_module._looks_like_orphan_compile_session
        is handoff_bundle_recovery.looks_like_orphan_compile_session
    )
    assert (
        service_module._reuse_terminal_compile_result
        is handoff_bundle_recovery.reuse_terminal_compile_result
    )
    assert (
        service_module._should_supersede_active_session
        is handoff_bundle_recovery.should_supersede_active_session
    )
    assert (
        service_module._build_compile_job_recovery_request
        is handoff_bundle_recovery.build_compile_job_recovery_request
    )


def test_handoff_bundle_helpers_do_not_add_runtime_entrypoints():
    sources = "\n".join(
        inspect.getsource(module)
        for module in (
            service_module,
            handoff_bundle_compile,
            handoff_bundle_recovery,
        )
    )

    forbidden_markers = [
        "APIRouter",
        "include_router",
        "PgBouncer",
        "setInterval",
        "setTimeout",
        "asyncio.create_task",
        "threading.Thread",
        "Queue(",
    ]
    for marker in forbidden_markers:
        assert marker not in sources
    assert "class HandoffBundleService" in inspect.getsource(service_module)
    assert "class HandoffBundleService" not in inspect.getsource(
        handoff_bundle_compile
    )
