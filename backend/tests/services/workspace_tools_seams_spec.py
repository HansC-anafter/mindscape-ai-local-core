from backend.app.services.tools.workspace_database_tool import (
    WorkspaceQueryDatabaseTool as HelperWorkspaceQueryDatabaseTool,
)
from backend.app.services.tools.workspace_execution_picker_tool import (
    WorkspacePickRelevantExecutionTool as HelperWorkspacePickRelevantExecutionTool,
)
from backend.app.services.tools.workspace_tools import (
    WorkspacePickRelevantExecutionTool,
    WorkspaceQueryDatabaseTool,
    create_workspace_tools,
    get_workspace_tool_by_name,
)


def test_workspace_tool_classes_remain_import_compatible_from_facade():
    assert WorkspacePickRelevantExecutionTool is HelperWorkspacePickRelevantExecutionTool
    assert WorkspaceQueryDatabaseTool is HelperWorkspaceQueryDatabaseTool


def test_create_workspace_tools_keeps_single_picker_and_database_tool(monkeypatch):
    monkeypatch.setattr(
        WorkspaceQueryDatabaseTool,
        "_collect_tables_from_registry",
        classmethod(lambda cls: ({"ig_accounts_flat"}, {"ig_accounts_flat"})),
    )

    tools = create_workspace_tools()
    names = [tool.metadata.name for tool in tools]

    assert names.count("workspace_pick_relevant_execution") == 1
    assert names.count("workspace_query_database") == 1


def test_workspace_tool_aliases_resolve_through_facade(monkeypatch):
    monkeypatch.setattr(
        WorkspaceQueryDatabaseTool,
        "_collect_tables_from_registry",
        classmethod(lambda cls: ({"ig_accounts_flat"}, {"ig_accounts_flat"})),
    )

    dotted_picker = get_workspace_tool_by_name("workspace.pick_relevant_execution")
    underscore_picker = get_workspace_tool_by_name("workspace_pick_relevant_execution")
    dotted_database = get_workspace_tool_by_name("workspace.query_database")
    underscore_database = get_workspace_tool_by_name("workspace_query_database")

    assert isinstance(dotted_picker, WorkspacePickRelevantExecutionTool)
    assert isinstance(underscore_picker, WorkspacePickRelevantExecutionTool)
    assert isinstance(dotted_database, WorkspaceQueryDatabaseTool)
    assert isinstance(underscore_database, WorkspaceQueryDatabaseTool)
