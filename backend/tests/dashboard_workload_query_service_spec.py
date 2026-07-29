from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from backend.app.services.dashboard_workload_query_service import (
    DashboardWorkloadQueryService,
)
from backend.app.dependencies.auth import AuthContext
from backend.app.models.dashboard import DashboardQuery
from backend.app.services.dashboard_aggregator import DashboardAggregator
from backend.app.services.stores.postgres.dashboard_workload_store import (
    DashboardWorkloadCounts,
    PostgresDashboardWorkloadStore,
)
from backend.app.utils.scope import ParsedScope


class _Result:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _Connection:
    def __init__(self, row):
        self.row = row
        self.statements = []

    def execute(self, statement, params):
        self.statements.append((str(statement), dict(params)))
        return _Result(self.row)


def _store_with_connection(connection):
    store = object.__new__(PostgresDashboardWorkloadStore)

    @contextmanager
    def connection_scope():
        yield connection

    store.get_connection = connection_scope
    return store


def test_store_counts_only_product_level_execution_entities():
    connection = _Connection(
        SimpleNamespace(
            open_cases=2,
            blocked_cases=1,
        )
    )
    store = _store_with_connection(connection)

    counts = store.load_counts(["workspace-1"])

    assert counts == DashboardWorkloadCounts(2, 1, 2)
    assert len(connection.statements) == 1
    sql, params = connection.statements[0]
    assert "playbook_executions" in sql
    assert "tasks" not in sql
    assert "SELECT *" not in sql.upper()
    assert params["workspace_ids"] == ["workspace-1"]


class _FacadeStore:
    def load_counts(self, workspace_ids):
        assert workspace_ids == ["workspace-1"]
        return DashboardWorkloadCounts(2, 1, 2)


@pytest.mark.asyncio
async def test_facade_does_not_project_runtime_tasks_as_assignments():
    service = DashboardWorkloadQueryService(_FacadeStore())

    counts = await service.load_counts(["workspace-1"])

    assert counts.open_assignments == 0
    assert counts.open_cases == 2
    assert counts.blocked_cases == 1
    assert counts.running_jobs == 2


@pytest.mark.asyncio
async def test_dashboard_exposes_assignment_semantic_gap_without_task_reads():
    aggregator = DashboardAggregator(
        SimpleNamespace(playbook_executions=object()),
        workload_query_service=object(),
    )
    auth = AuthContext(
        user_id="user-1",
        tenant_id="local",
        workspace_ids=["workspace-1"],
    )
    scope = ParsedScope(type="workspace", id="workspace-1")
    query = DashboardQuery(limit=50, offset=0)

    inbox = await aggregator.get_inbox(auth, query, scope)
    assignments = await aggregator.get_assignments(auth, query, scope)

    assert inbox.total == 0
    assert assignments.total == 0
    assert any(
        "runtime tasks are not user assignments" in warning
        for warning in inbox.warnings
    )
    assert any(
        "runtime tasks are not user assignments" in warning
        for warning in assignments.warnings
    )
