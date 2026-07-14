from pathlib import Path

from backend.app.services import capability_registry
from backend.app.services.stores.installed_packs_store import InstalledPacksStore
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


def test_workspace_database_catalog_reads_enabled_manifests_without_runtime_load(
    tmp_path: Path,
    monkeypatch,
):
    pack_dir = tmp_path / "demo_pack"
    pack_dir.mkdir()
    (pack_dir / "manifest.yaml").write_text(
        (
            "code: demo_pack\n"
            "queryable_tables:\n"
            "  - name: demo_rows\n"
            "    workspace_scoped: true\n"
            "  - global_lookup\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        WorkspaceQueryDatabaseTool,
        "_installed_capabilities_dir",
        classmethod(lambda cls: tmp_path),
    )
    monkeypatch.setattr(
        InstalledPacksStore,
        "list_enabled_pack_ids",
        lambda self: ["demo_pack"],
    )
    monkeypatch.setattr(
        capability_registry,
        "load_capabilities",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("workspace tool catalog must not load capability runtimes")
        ),
    )

    allowed, scoped = WorkspaceQueryDatabaseTool._collect_tables_from_registry()

    assert allowed == {"demo_rows", "global_lookup"}
    assert scoped == {"demo_rows", "global_lookup"}
