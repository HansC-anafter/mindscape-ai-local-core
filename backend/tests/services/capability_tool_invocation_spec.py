from types import MappingProxyType

import pytest

from backend.app.services.capability_tool_invocation import (
    CapabilityExecutionContext,
    RuntimeTaskIdentity,
    build_capability_execution_context,
    current_runtime_task_identity,
    invoke_capability_tool,
    invoke_capability_tool_async,
    runtime_task_identity_scope,
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


def test_verified_snapshot_is_authoritative_for_standard_tool_identity():
    context = build_capability_execution_context(
        {
            "workspace_id": "workspace-unverified",
            "execution_id": None,
            "trace_id": "trace-unverified",
        },
        admission_snapshot={
            "workspace_id": "workspace-verified",
            "root_execution_id": "execution-verified",
            "trace_id": "trace-verified",
        },
        runtime_task_identity=RuntimeTaskIdentity("task-current"),
    )

    assert context.workspace_id == "workspace-verified"
    assert context.execution_id == "execution-verified"
    assert context.task_id == "task-current"
    assert context.root_execution_id == "execution-verified"
    assert context.trace_id == "trace-verified"


def test_explicit_context_is_not_rebuilt_from_sanitized_inputs():
    expected = CapabilityExecutionContext(
        workspace_id="workspace-1",
        project_id=None,
        execution_id="execution-1",
        task_id="task-1",
        root_execution_id="execution-1",
        trace_id="trace-1",
        profile_id=None,
        admission_snapshot=MappingProxyType({"snapshot_hash": "verified"}),
    )

    def standard_tool(inputs, ctx):
        return inputs, ctx

    inputs, context = invoke_capability_tool(
        standard_tool,
        {"value": 11},
        execution_context=expected,
    )

    assert inputs == {"value": 11}
    assert context is expected


def test_runtime_task_identity_scope_is_typed_and_resets():
    assert current_runtime_task_identity() is None

    with runtime_task_identity_scope(" task-current ") as identity:
        assert identity == RuntimeTaskIdentity("task-current")
        assert current_runtime_task_identity() is identity

    assert current_runtime_task_identity() is None
