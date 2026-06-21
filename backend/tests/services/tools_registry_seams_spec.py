from __future__ import annotations

from types import SimpleNamespace

from backend.app.services.tools import registry
from backend.app.services.tools.base import ToolConnection
from backend.app.services.tools.registry_core import builtin
from backend.app.services.tools.registry_core import state


class FakeLegacyTool:
    def __init__(self, connection):
        self.connection = connection


class FakeTool:
    def __init__(self, name: str):
        self.metadata = SimpleNamespace(name=name)

    def to_dict(self):
        return {"name": self.metadata.name}


def clear_registry_state():
    registry._dynamic_tools.clear()
    registry._mindscape_tools.clear()


def test_public_facade_uses_core_shared_state_objects():
    assert registry._dynamic_tools is state._dynamic_tools
    assert registry._mindscape_tools is state._mindscape_tools
    assert registry.STATIC_TOOL_REGISTRY is state.STATIC_TOOL_REGISTRY


def test_dynamic_registration_and_legacy_wp_lookup_share_state(monkeypatch):
    clear_registry_state()
    connection = ToolConnection(id="site1", tool_type="wordpress")
    monkeypatch.setitem(registry.STATIC_TOOL_REGISTRY["wordpress"], "local", FakeLegacyTool)

    registry.register_dynamic_tool("wp.site1.post.create_draft", connection)
    tool = registry.get_tool_by_registered_id("wp.site1.post.create_draft")

    assert isinstance(tool, FakeLegacyTool)
    assert tool.connection is connection
    assert registry.get_dynamic_tools_for_site("site1") == ["wp.site1.post.create_draft"]


def test_unregister_dynamic_tool_removes_dynamic_and_mindscape_entries():
    clear_registry_state()
    connection = ToolConnection(id="site1", tool_type="wordpress")
    tool = FakeTool("wp.site1.post.create_draft")

    registry.register_dynamic_tool("wp.site1.post.create_draft", connection)
    registry.register_mindscape_tool("wp.site1.post.create_draft", tool)
    registry.unregister_dynamic_tool("wp.site1.post.create_draft")

    assert registry.get_tool_by_registered_id("wp.site1.post.create_draft") is None
    assert registry.get_mindscape_tool("wp.site1.post.create_draft") is None


def test_workspace_registration_keeps_dot_notation_alias(monkeypatch):
    clear_registry_state()
    tool = FakeTool("workspace_get_execution")

    monkeypatch.setattr(
        "backend.app.services.tools.workspace_tools.create_workspace_tools",
        lambda: [tool],
    )

    assert registry.register_workspace_tools() == [tool]
    assert registry.get_mindscape_tool("workspace_get_execution") is tool
    assert registry.get_mindscape_tool("workspace.get_execution") is tool


def test_reporting_registration_keeps_core_alias(monkeypatch):
    clear_registry_state()
    tool = FakeTool("workspace_write_html_report")

    monkeypatch.setattr(builtin, "register_mindscape_tool", registry.register_mindscape_tool)
    monkeypatch.setattr(
        "backend.app.services.tools.reporting.create_reporting_tools",
        lambda: [tool],
    )

    assert registry.register_reporting_tools() == [tool]
    assert registry.get_tool_metadata("workspace_write_html_report") == {
        "name": "workspace_write_html_report"
    }
    assert registry.get_mindscape_tool("core.workspace_write_html_report") is tool
