import sys
import types

import pytest

from backend.app.services.object_runtime.common import _invoke_backend_callable


@pytest.mark.asyncio
async def test_object_runtime_backend_callable_reloads_loaded_module_when_attr_is_missing(
    monkeypatch,
):
    module_name = "backend.tests._fake_object_runtime_reloaded_backend"
    fake_module = types.ModuleType(module_name)
    reload_calls = []

    def reload_module(module):
        reload_calls.append(module.__name__)

        def project(workspace_id: str):
            return {"workspace_id": workspace_id, "reloaded": True}

        module.project = project
        return module

    monkeypatch.setitem(sys.modules, module_name, fake_module)
    monkeypatch.setattr(
        "backend.app.services.object_runtime.common.importlib.reload",
        reload_module,
    )

    result = await _invoke_backend_callable(
        f"{module_name}:project",
        workspace_id="ws_demo",
    )

    assert reload_calls == [module_name]
    assert result == {"workspace_id": "ws_demo", "reloaded": True}


@pytest.mark.asyncio
async def test_object_runtime_backend_callable_resolves_core_host_resource_facade():
    result = await _invoke_backend_callable(
        "backend.app.services.object_runtime.core_host_resource_objects:plan_preview_route_intent",
        workspace_id="ws_demo",
        role_assignments=[],
        request_context={},
    )

    assert result["action"] == "preview_route_intent"
    assert result["route_request"]["workspace_id"] == "ws_demo"
    assert result["request_context"]["resource_mutation"] == "none"
