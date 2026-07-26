from types import MappingProxyType

import pytest

from backend.app.services.capability_tool_invocation import (
    CapabilityExecutionContext,
    invoke_capability_tool,
    invoke_capability_tool_async,
)


def test_standard_signature_receives_copied_inputs_and_immutable_context():
    original = {
        "value": 7,
        "workspace_id": "workspace-1",
        "execution_admission_snapshot": {"snapshot_hash": "abc"},
    }

    def standard_tool(inputs, ctx):
        inputs["value"] = 9
        return inputs, ctx

    inputs, context = invoke_capability_tool(standard_tool, original)

    assert original["value"] == 7
    assert inputs["value"] == 9
    assert isinstance(context, CapabilityExecutionContext)
    assert context.workspace_id == "workspace-1"
    assert isinstance(context.admission_snapshot, MappingProxyType)


@pytest.mark.asyncio
async def test_async_standard_signature_is_awaited():
    async def standard_tool(inputs, ctx):
        return {"value": inputs["value"], "execution_id": ctx.execution_id}

    result = await invoke_capability_tool_async(
        standard_tool,
        {"value": 3, "execution_id": "execution-1"},
    )

    assert result == {"value": 3, "execution_id": "execution-1"}


def test_legacy_keyword_signature_remains_unchanged():
    def legacy_tool(value, enabled=False):
        return value, enabled

    assert invoke_capability_tool(
        legacy_tool,
        {"value": 5, "enabled": True},
    ) == (5, True)
