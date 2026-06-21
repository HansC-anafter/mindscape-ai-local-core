from types import SimpleNamespace
import inspect

import pytest

from backend.app.services.unified_tool_executor import (
    ToolExecutionResult,
    UnifiedToolExecutor,
    _inject_runtime_context,
    _resolve_backend_target,
)


class _FakeTool:
    description = "Fake tool"
    metadata = SimpleNamespace(source_type="fake")

    def __init__(self):
        self.calls = []

    async def safe_execute(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            success=True,
            result={"ok": True},
            error=None,
            metadata={"call_count": len(self.calls)},
        )


class _NestedResultTool:
    description = "Nested tool"
    metadata = SimpleNamespace(source_type="nested")

    async def safe_execute(self, **kwargs):
        return SimpleNamespace(
            success=True,
            result=SimpleNamespace(
                success=True,
                result={"inner": True},
                error=None,
                metadata={"inner_meta": "kept"},
            ),
            error=None,
            metadata={"outer_meta": "kept"},
        )


def test_public_facade_preserves_executor_and_result_shapes() -> None:
    result = ToolExecutionResult(
        success=True,
        tool_name="builtin.echo",
        tool_type="builtin",
        result={"value": 1},
        metadata={"source": "test"},
    )
    executor = UnifiedToolExecutor(mcp_manager=object(), tool_resolver=object())

    assert result.to_dict()["metadata"] == {"source": "test"}
    assert executor._parse_tool_name("default.echo") == ("builtin", "echo")
    assert executor._parse_tool_name("mcp.github") == ("mcp", "github")
    assert hasattr(executor, "execute_tool_dependency")
    assert hasattr(executor, "_resolve_capability_tool")


@pytest.mark.asyncio
async def test_execute_tool_calls_safe_execute_once_and_records_history() -> None:
    tool = _FakeTool()
    executor = UnifiedToolExecutor(mcp_manager=object(), tool_resolver=object())

    async def fake_get_tool(tool_type, tool_name):
        assert (tool_type, tool_name) == ("builtin", "echo")
        return tool

    executor._get_tool = fake_get_tool

    result = await executor.execute_tool("default.echo", {"text": "hi"})

    assert result.success is True
    assert result.result == {"ok": True}
    assert result.metadata["tool_description"] == "Fake tool"
    assert result.metadata["tool_source"] == "fake"
    assert result.metadata["call_count"] == 1
    assert tool.calls == [{"text": "hi"}]
    assert len(executor.get_execution_history()) == 1
    assert executor.get_statistics()["tool_type_distribution"] == {"builtin": 1}


@pytest.mark.asyncio
async def test_execute_tool_unwraps_nested_tool_execution_result_once() -> None:
    executor = UnifiedToolExecutor(mcp_manager=object(), tool_resolver=object())

    async def fake_get_tool(tool_type, tool_name):
        return _NestedResultTool()

    executor._get_tool = fake_get_tool

    result = await executor.execute_tool("nested", {"value": 1})

    assert result.success is True
    assert result.result == {"inner": True}
    assert result.error is None
    assert result.metadata["outer_meta"] == "kept"
    assert result.metadata["inner_meta"] == "kept"


@pytest.mark.asyncio
async def test_execute_tool_returns_not_found_without_history_mutation() -> None:
    executor = UnifiedToolExecutor(mcp_manager=object(), tool_resolver=object())

    async def missing_tool(tool_type, tool_name):
        return None

    executor._get_tool = missing_tool

    result = await executor.execute_tool("missing", {})

    assert result.success is False
    assert result.tool_type == "builtin"
    assert result.error == "Tool missing not found or not registered"
    assert executor.get_execution_history() == []


def test_runtime_context_injection_preserves_parameter_names() -> None:
    def tool(runtime_context=None, execution_context=None):
        return runtime_context, execution_context

    injected = _inject_runtime_context({"value": 1}, inspect.signature(tool))

    assert injected["value"] == 1
    assert "service_endpoints" in injected["runtime_context"]
    assert injected["execution_context"] == {
        "runtime_context": injected["runtime_context"]
    }


def test_resolve_backend_target_supports_dotted_class_methods() -> None:
    class FakeModule:
        class Service:
            def run(self, value):
                return {"value": value}

    target = _resolve_backend_target(FakeModule, "Service.run")

    assert callable(target)
    assert target("ok") == {"value": "ok"}
