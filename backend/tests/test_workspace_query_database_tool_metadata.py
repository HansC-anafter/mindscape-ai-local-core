from backend.app.services.tools.workspace_tools import WorkspaceQueryDatabaseTool


def test_workspace_query_database_tool_description_stays_within_limit(monkeypatch):
    table_names = {f"table_{idx:03d}" for idx in range(80)}
    monkeypatch.setattr(
        WorkspaceQueryDatabaseTool,
        "_collect_tables_from_registry",
        staticmethod(lambda: (table_names, table_names)),
    )

    tool = WorkspaceQueryDatabaseTool()

    assert len(tool.metadata.description) <= 500
    assert "SELECT" in tool.metadata.description
    assert "workspace_id" in tool.metadata.description
