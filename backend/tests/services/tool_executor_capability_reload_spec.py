from unittest.mock import MagicMock

import pytest

from backend.app.shared import tool_executor as tool_executor_module
from backend.app.services import capability_registry
from backend.app.services.tool_slot_resolver import ToolSlotResolver


@pytest.mark.asyncio
async def test_capability_tool_miss_reloads_only_requested_pack(monkeypatch):
    registry = MagicMock()
    registry.get_tool.side_effect = [None, {"backend": "demo.backend:run"}]
    reloaded = []

    monkeypatch.setattr(tool_executor_module, "get_registry", lambda: registry)
    monkeypatch.setattr(
        tool_executor_module,
        "reload_capability",
        lambda capability_code: reloaded.append(capability_code) or True,
    )

    async def fake_call_tool_async(capability, tool, **kwargs):
        return {"capability": capability, "tool": tool, "kwargs": kwargs}

    monkeypatch.setattr(
        tool_executor_module,
        "call_tool_async",
        fake_call_tool_async,
    )

    executor = tool_executor_module.ToolExecutor()
    result = await executor.execute_tool("demo_pack.inspect", subject="sample")

    assert reloaded == ["demo_pack"]
    assert result == {
        "capability": "demo_pack",
        "tool": "inspect",
        "kwargs": {"subject": "sample"},
    }


def test_tool_slot_resolution_reloads_only_requested_pack(monkeypatch):
    registry = MagicMock()
    registry.get_tool.side_effect = [None, {"backend": "demo.backend:run"}]
    reloaded = []
    monkeypatch.setattr(capability_registry, "get_registry", lambda: registry)
    monkeypatch.setattr(
        capability_registry,
        "reload_capability",
        lambda capability_code: reloaded.append(capability_code) or True,
    )

    resolver = ToolSlotResolver(store=MagicMock())

    assert resolver._is_registered_capability_tool("demo_pack.inspect") is True
    assert reloaded == ["demo_pack"]
