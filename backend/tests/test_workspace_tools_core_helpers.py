from datetime import datetime, timedelta, timezone

import pytest

from backend.app.services.tools.schemas import ToolMetadata
from backend.app.services.tools.workspace_tools import WorkspaceQueryDatabaseTool
from backend.app.services.tools.workspace_tools_core.errors import (
    WorkspaceQueryValidationError,
)
from backend.app.services.tools.workspace_tools_core.query_validation import (
    parse_table_refs,
    strip_sql_comments,
    strip_sql_string_literals,
    validate_workspace_query,
)
from backend.app.services.tools.workspace_tools_core.utils import (
    select_recent_candidates,
    task_to_payload,
)


class _DumpableTask:
    def model_dump(self, mode="json"):
        return {"id": "task-1", "status": "running"}


class _PlainTask:
    def __init__(self):
        self.id = "task-2"
        self.status = "queued"


def test_task_to_payload_supports_model_dump_dict_and_object():
    assert task_to_payload(_DumpableTask()) == {"id": "task-1", "status": "running"}
    assert task_to_payload({"id": "task-3"}) == {"id": "task-3"}
    assert task_to_payload(_PlainTask()) == {"id": "task-2", "status": "queued"}


def test_select_recent_candidates_filters_by_recent_window():
    now = datetime(2026, 3, 24, 12, 0, tzinfo=timezone.utc)
    candidates = [
        {"execution_id": "recent", "created_at": now.isoformat()},
        {"execution_id": "old", "created_at": (now - timedelta(minutes=10)).isoformat()},
        {"execution_id": "bad", "created_at": "not-a-date"},
    ]

    result = select_recent_candidates(candidates, now=now)

    assert [candidate["execution_id"] for candidate in result] == ["recent"]


def test_strip_helpers_remove_comments_and_ignore_string_literals():
    sql = "SELECT * FROM ig_accounts_flat -- comment\nWHERE bio LIKE '%copy%'"

    stripped = strip_sql_comments(sql)
    sanitized = strip_sql_string_literals(stripped)

    assert "-- comment" not in stripped
    assert "'%copy%'" not in sanitized
    assert "'__STR__'" in sanitized


def test_parse_table_refs_keeps_aliases():
    refs = parse_table_refs(
        "SELECT * FROM ig_accounts_flat AS a JOIN ig_posts p ON p.account_id = a.id"
    )

    assert refs == [("ig_accounts_flat", "a"), ("ig_posts", "p")]


def test_validate_workspace_query_injects_workspace_filters_and_caps_limit():
    query = validate_workspace_query(
        "SELECT a.id FROM ig_accounts_flat a JOIN ig_posts p ON p.account_id = a.id LIMIT 500",
        "ws-1",
        allowed_tables={"ig_accounts_flat", "ig_posts"},
        workspace_scoped_tables={"ig_accounts_flat", "ig_posts"},
        max_rows=100,
    )

    assert "WHERE a.workspace_id = %s AND p.workspace_id = %s" in query
    assert query.endswith("LIMIT 100")


def test_validate_workspace_query_blocks_multi_statement():
    with pytest.raises(WorkspaceQueryValidationError, match="Multi-statement"):
        validate_workspace_query(
            "SELECT * FROM ig_accounts_flat; SELECT * FROM ig_posts",
            "ws-1",
            allowed_tables={"ig_accounts_flat", "ig_posts"},
            workspace_scoped_tables={"ig_accounts_flat", "ig_posts"},
            max_rows=100,
        )


def test_workspace_query_database_tool_wrapper_uses_core_validator():
    tool = WorkspaceQueryDatabaseTool.__new__(WorkspaceQueryDatabaseTool)
    tool.ALLOWED_TABLES = {"ig_accounts_flat"}
    tool.WORKSPACE_SCOPED_TABLES = {"ig_accounts_flat"}
    tool.MAX_ROWS = 25

    query = tool._validate_query(
        "SELECT id FROM ig_accounts_flat WHERE bio LIKE '%copy%'",
        "ws-1",
    )

    assert query == (
        "SELECT id FROM ig_accounts_flat WHERE ig_accounts_flat.workspace_id = %s "
        "AND bio LIKE '%%copy%%' LIMIT 25"
    )


def test_workspace_query_database_tool_summarizes_large_table_sets(monkeypatch):
    tables = {f"table_{index:02d}" for index in range(20)}

    monkeypatch.setattr(
        WorkspaceQueryDatabaseTool,
        "_collect_tables_from_registry",
        classmethod(lambda cls: (tables, tables)),
    )

    tool = WorkspaceQueryDatabaseTool()

    assert isinstance(tool.metadata, ToolMetadata)
    assert len(tool.metadata.description) <= 500
    assert "+12 more" in tool.metadata.description
    assert "table_19" not in tool.metadata.description
    sql_query_description = tool.metadata.input_schema.properties["sql_query"]["description"]
    assert "Allowed tables include:" in sql_query_description
    assert "table_19" not in sql_query_description
