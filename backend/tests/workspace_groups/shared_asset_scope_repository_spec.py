from contextlib import contextmanager
from types import SimpleNamespace

from backend.app.services.workspace_groups.shared_asset_scope_repository import (
    SharedAssetScopeRepository,
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


def test_repository_loads_all_scope_evidence_in_one_bounded_statement():
    row = SimpleNamespace(
        binding_id="binding-1",
        active_workspace_id="consumer",
        active_workspace_owner_user_id="owner",
        consumer_access_mode="read",
        consumer_overrides={"group_id": "group-1"},
        resource_id="ig-seed:sinnie_withu",
        source_binding_id="source-binding",
        source_workspace_id="source",
        source_workspace_title="Source Workspace",
        source_access_mode="read",
        source_overrides={"group_id": "group-1"},
        group_id="group-1",
        group_title="Group 1",
        group_owner_user_id="owner",
        group_revision=3,
        consumer_is_member=True,
        source_is_member=True,
        topology_is_ready=True,
    )
    connection = FakeConnection([row])
    repository = object.__new__(SharedAssetScopeRepository)

    @contextmanager
    def connection_scope():
        yield connection

    repository.get_connection = connection_scope
    evidence = repository.list_evidence(
        workspace_id="consumer",
        group_id=None,
    )

    assert len(evidence) == 1
    assert evidence[0].source_workspace_id == "source"
    assert len(connection.statements) == 1
    sql, params = connection.statements[0]
    assert "active_workspace.id = :workspace_id" in sql
    assert "LEFT JOIN workspace_resource_bindings AS consumer" in sql
    assert "LEFT JOIN LATERAL" in sql
    assert "candidate.access_mode = 'read'" in sql
    assert "candidate.overrides->'dynamic_selector'" in sql
    assert "AS jsonb" in sql
    assert "workspace_group_memberships" in sql
    assert "ORDER BY" in sql
    assert params == {"workspace_id": "consumer", "group_id": None}
