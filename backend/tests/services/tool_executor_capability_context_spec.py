import pytest

from backend.app.services import tool_execution_admission
from backend.app.services.capability_tool_invocation import (
    runtime_task_identity_scope,
)
from backend.app.services.playbook.tool_execution.normalization import (
    ToolParameterNormalizer,
)
from backend.app.shared import tool_executor as tool_executor_module


class _CapabilityRegistry:
    def get_tool(self, tool_name):
        if tool_name == "ig.ig_analyze_following":
            return {"backend": "unused:test"}
        return None


@pytest.mark.asyncio
async def test_tool_executor_separates_verified_context_from_sanitized_inputs(
    monkeypatch,
):
    captured = {}

    async def fake_prepare_tool_admission(*, tool_name, arguments):
        assert tool_name == "ig.ig_analyze_following"
        assert arguments["trace_id"] == "templated-trace"
        return (
            {
                "workspace_id": "workspace-1",
                "target_username": "target",
            },
            {
                "workspace_id": "workspace-1",
                "root_execution_id": "execution-1",
                "trace_id": "verified-trace",
                "snapshot_hash": "verified",
            },
        )

    async def fake_call_tool_async(
        capability,
        tool,
        *,
        _execution_context=None,
        **kwargs,
    ):
        captured["capability"] = capability
        captured["tool"] = tool
        captured["context"] = _execution_context
        captured["kwargs"] = kwargs
        return {"status": "succeeded"}

    monkeypatch.setattr(
        tool_execution_admission,
        "prepare_tool_admission",
        fake_prepare_tool_admission,
    )
    monkeypatch.setattr(
        tool_executor_module,
        "call_tool_async",
        fake_call_tool_async,
    )

    executor = tool_executor_module.ToolExecutor()
    executor.registry = _CapabilityRegistry()
    normalized = ToolParameterNormalizer.normalize(
        "ig.ig_analyze_following",
        {
            "workspace_id": "workspace-1",
            "target_username": "target",
            "trace_id": "templated-trace",
            "_runtime_task_identity": "untrusted",
        },
        execution_context={"task_id": "task-current"},
    )
    assert "_runtime_task_identity" not in normalized
    with runtime_task_identity_scope("task-current"):
        result = await executor.execute_tool(
            "ig.ig_analyze_following",
            **normalized,
            execution_admission_snapshot={"snapshot_hash": "unverified-input"},
        )

    assert result == {"status": "succeeded"}
    assert captured["capability"] == "ig"
    assert captured["tool"] == "ig_analyze_following"
    assert captured["kwargs"] == {
        "workspace_id": "workspace-1",
        "target_username": "target",
    }
    assert captured["context"].execution_id == "execution-1"
    assert captured["context"].task_id == "task-current"
    assert captured["context"].root_execution_id == "execution-1"
    assert captured["context"].trace_id == "verified-trace"
    assert captured["context"].admission_snapshot["snapshot_hash"] == "verified"
