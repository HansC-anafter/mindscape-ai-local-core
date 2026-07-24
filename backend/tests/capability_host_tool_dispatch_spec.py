"""Contract tests for the installed-capability tool dispatch facade."""

from __future__ import annotations

import pytest

import backend.app.capability_host.tool_dispatch as tool_dispatch


@pytest.mark.asyncio
async def test_dispatch_calls_registry_once_with_json_copy(monkeypatch):
    calls = []

    async def _call(capability, tool, **arguments):
        calls.append((capability, tool, arguments))
        return {"status": "accepted"}

    monkeypatch.setattr(tool_dispatch, "_call_tool_async", _call)
    source_arguments = {
        "workspace_id": "workspace-1",
        "candidate_count": 4,
    }
    result = await tool_dispatch.dispatch_capability_tool(
        "comfyui_runtime.comfyui_dispatch_visual_intent_run",
        source_arguments,
    )

    assert result == {"status": "accepted"}
    assert calls == [
        (
            "comfyui_runtime",
            "comfyui_dispatch_visual_intent_run",
            source_arguments,
        )
    ]
    assert calls[0][2] is not source_arguments


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_fqn",
    [
        "",
        "comfyui_runtime",
        "comfyui_runtime.tool.extra",
        "ComfyUI.tool",
        "filesystem_write_file",
    ],
)
async def test_dispatch_rejects_non_capability_fqn(monkeypatch, tool_fqn):
    async def _unexpected(*_args, **_kwargs):
        raise AssertionError("registry must not be called")

    monkeypatch.setattr(tool_dispatch, "_call_tool_async", _unexpected)
    with pytest.raises(ValueError, match="capability_tool_dispatch_fqn_invalid"):
        await tool_dispatch.dispatch_capability_tool(tool_fqn, {})


@pytest.mark.asyncio
async def test_dispatch_rejects_non_json_and_oversized_arguments(monkeypatch):
    async def _unexpected(*_args, **_kwargs):
        raise AssertionError("registry must not be called")

    monkeypatch.setattr(tool_dispatch, "_call_tool_async", _unexpected)
    with pytest.raises(
        ValueError,
        match="capability_tool_dispatch_arguments_json_required",
    ):
        await tool_dispatch.dispatch_capability_tool(
            "comfyui_runtime.tool",
            {"invalid": object()},
        )
    with pytest.raises(
        ValueError,
        match="capability_tool_dispatch_arguments_too_large",
    ):
        await tool_dispatch.dispatch_capability_tool(
            "comfyui_runtime.tool",
            {"payload": "x" * tool_dispatch.TOOL_ARGUMENTS_MAX_BYTES},
        )
