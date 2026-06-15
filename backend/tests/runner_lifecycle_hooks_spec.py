from __future__ import annotations

import asyncio
from types import SimpleNamespace

from backend.app.runner.lifecycle_hooks import _invoke_on_fail_hook


def test_on_fail_hook_reloads_capabilities_when_registry_misses(monkeypatch) -> None:
    calls = {
        "get_tool_backend": 0,
        "load_capabilities": 0,
    }

    def fake_get_tool_backend(capability: str, tool: str):
        calls["get_tool_backend"] += 1
        assert capability == "decision_assets"
        assert tool == "decision_assets_mark_request_terminal"
        if calls["get_tool_backend"] == 1:
            return None
        return "fake.lifecycle:hook"

    def fake_load_capabilities(*_args, **_kwargs):
        calls["load_capabilities"] += 1

    invoked = []

    def fake_hook(**kwargs):
        invoked.append(kwargs)
        return {"status": "failed"}

    monkeypatch.setattr(
        "backend.app.services.capability_registry.get_tool_backend",
        fake_get_tool_backend,
    )
    monkeypatch.setattr(
        "backend.app.services.capability_registry.load_capabilities",
        fake_load_capabilities,
    )
    monkeypatch.setattr(
        "importlib.import_module",
        lambda module_path: (
            SimpleNamespace(hook=fake_hook)
            if module_path == "fake.lifecycle"
            else __import__(module_path)
        ),
    )

    result = asyncio.run(
        _invoke_on_fail_hook(
            execution_context={
                "inputs": {
                    "workspace_id": "ws_test",
                    "request_id": "dar_test",
                },
                "lifecycle_hooks": {
                    "on_fail": {
                        "tool_slot": "decision_assets.decision_assets_mark_request_terminal",
                        "inputs_map": {
                            "workspace_id": "{{input.workspace_id}}",
                            "request_id": "{{input.request_id}}",
                            "task_id": "{{context.task_id}}",
                            "failure_reason": "{{context.error}}",
                        },
                    }
                },
            },
            failure_reason="decision_assets_runtime_request_failed:[Errno 111] Connection refused",
            task_id="task_test",
        )
    )

    assert result is True
    assert calls["get_tool_backend"] == 2
    assert calls["load_capabilities"] == 1
    assert invoked == [
        {
            "workspace_id": "ws_test",
            "request_id": "dar_test",
            "task_id": "task_test",
            "failure_reason": "decision_assets_runtime_request_failed:[Errno 111] Connection refused",
            "execution_context": {
                "inputs": {
                    "workspace_id": "ws_test",
                    "request_id": "dar_test",
                },
                "lifecycle_hooks": {
                    "on_fail": {
                        "tool_slot": "decision_assets.decision_assets_mark_request_terminal",
                        "inputs_map": {
                            "workspace_id": "{{input.workspace_id}}",
                            "request_id": "{{input.request_id}}",
                            "task_id": "{{context.task_id}}",
                            "failure_reason": "{{context.error}}",
                        },
                    }
                },
            },
        }
    ]
