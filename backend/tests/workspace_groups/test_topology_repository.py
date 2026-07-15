from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

from backend.app.services.workspace_groups.topology_repository import (
    WorkspaceGroupTopologyRepository,
)


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, rows):
        self.rows = rows
        self.statements = []

    def execute(self, statement, params):
        self.statements.append((str(statement), params))
        return FakeResult(self.rows)


def test_group_list_is_one_bounded_aggregate_statement():
    now = datetime.now(timezone.utc)
    row = SimpleNamespace(
        id="group-1",
        display_name="Group 1",
        owner_user_id="owner",
        description=None,
        metadata={},
        revision=2,
        members=[{"workspace_id": "ws-1", "role": "dispatch"}],
        created_at=now,
        updated_at=now,
    )
    connection = FakeConnection([row])
    repository = object.__new__(WorkspaceGroupTopologyRepository)

    @contextmanager
    def connection_scope():
        yield connection

    repository.get_connection = connection_scope
    groups = repository.list_authorized(
        actor_user_id="owner",
        allowed_group_ids=[],
        limit=500,
    )

    assert len(groups) == 1
    assert len(connection.statements) == 1
    sql, params = connection.statements[0]
    assert "jsonb_agg" in sql
    assert "LIMIT" in sql
    assert params["limit"] == 200
