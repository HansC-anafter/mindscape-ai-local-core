from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from backend.app.services.conversation.context_builder.tool_context import (
    build_tool_context_section,
)


@pytest.mark.asyncio
async def test_build_tool_context_section_backfills_bound_tools():
    binding_store = Mock()
    binding_store.list_bindings_by_workspace.return_value = [
        SimpleNamespace(resource_id="tool.alpha", overrides={}),
        SimpleNamespace(
            resource_id="tool.beta",
            overrides={"display_name": "Beta Display"},
        ),
    ]

    with patch(
        "backend.app.services.tool_rag.retrieve_relevant_tools",
        new=AsyncMock(
            return_value=[{"tool_id": "tool.alpha", "display_name": "Alpha"}]
        ),
    ), patch(
        "backend.app.services.stores.workspace_resource_binding_store.WorkspaceResourceBindingStore",
        return_value=binding_store,
    ):
        section = await build_tool_context_section(
            message="find tools",
            workspace_id="ws_123",
        )

    assert section[0] == "\n## Available Tools (relevant to your request):"
    assert "- tool.alpha: Alpha" in section[1]
    assert "- tool.beta: Beta Display" in section[1]
