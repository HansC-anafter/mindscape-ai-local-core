import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from backend.app.models.task_ir import PhaseIR
from backend.app.services.orchestration.dispatch_orchestrator_core.runtime_context import (
    create_attempt,
)
from backend.app.services.workspace_groups.contracts import (
    ActiveWorkspaceGroupContext,
    WorkspaceGroupTopology,
    WorkspaceGroupTopologySnapshot,
)
from backend.app.services.workspace_groups.execution_facade import (
    GroupExecutionFacade,
    WorkspaceGroupExecutionBoundaryError,
)
from backend.app.services.workspace_groups.snapshot_service import (
    WorkspaceGroupSnapshotService,
)


class SnapshotConnection:
    def __init__(self):
        self.calls = []

    def execute(self, statement, params):
        self.calls.append((str(statement), params))
        payload = json.loads(params["payload"])
        row = SimpleNamespace(
            id=params["id"],
            group_id=params["group_id"],
            group_revision=params["group_revision"],
            content_hash=params["content_hash"],
            payload=payload,
            created_by_user_id=params["created_by_user_id"],
            created_at=None,
        )
        return SimpleNamespace(fetchone=lambda: row)


def _context():
    topology = WorkspaceGroupTopology(
        id="group-1",
        display_name="Group 1",
        owner_user_id="owner",
        revision=5,
        members=[
            {"workspace_id": "dispatch", "role": "dispatch"},
            {"workspace_id": "cell", "role": "cell"},
        ],
    )
    return ActiveWorkspaceGroupContext(
        group_id="group-1",
        workspace_id="dispatch",
        role="dispatch",
        revision=5,
        topology=topology,
    )


def test_snapshot_admission_is_one_deduplicating_statement():
    connection = SnapshotConnection()
    service = object.__new__(WorkspaceGroupSnapshotService)

    @contextmanager
    def transaction():
        yield connection

    service.transaction = transaction
    snapshot = service.get_or_create(_context(), actor_user_id="owner")

    assert len(connection.calls) == 1
    sql, _ = connection.calls[0]
    assert "ON CONFLICT" in sql and "UNION ALL" in sql
    assert snapshot.group_revision == 5
    assert snapshot.role_map == {"dispatch": "dispatch", "cell": "cell"}


def test_execution_boundary_requires_snapshot_for_cross_workspace_target():
    single = GroupExecutionFacade(workspace_id="dispatch", snapshot=None)
    assert single.validate_target("dispatch") == "dispatch"
    with pytest.raises(WorkspaceGroupExecutionBoundaryError):
        single.validate_target("cell")

    snapshot = WorkspaceGroupTopologySnapshot(
        id="snapshot-1",
        group_id="group-1",
        display_name="Group 1",
        group_revision=5,
        content_hash="a" * 64,
        members=[
            {"workspace_id": "dispatch", "role": "dispatch"},
            {"workspace_id": "cell", "role": "cell"},
        ],
        dispatch_workspace_id="dispatch",
        cell_workspace_ids=["cell"],
        created_by_user_id="owner",
    )
    grouped = GroupExecutionFacade(workspace_id="dispatch", snapshot=snapshot)
    assert grouped.validate_target("cell") == "cell"
    with pytest.raises(WorkspaceGroupExecutionBoundaryError):
        grouped.validate_target("outside")


def test_phase_attempt_carries_the_admission_snapshot_id():
    snapshot = WorkspaceGroupTopologySnapshot(
        id="snapshot-1",
        group_id="group-1",
        display_name="Group 1",
        group_revision=5,
        content_hash="a" * 64,
        members=[{"workspace_id": "dispatch", "role": "dispatch"}],
        dispatch_workspace_id="dispatch",
        created_by_user_id="owner",
    )
    orchestrator = SimpleNamespace(
        _attempts={},
        _group_execution=GroupExecutionFacade(
            workspace_id="dispatch", snapshot=snapshot
        ),
    )
    attempt = create_attempt(
        orchestrator,
        PhaseIR(id="phase-1", name="Phase 1"),
        "task-1",
    )
    assert attempt.workspace_group_snapshot_id == "snapshot-1"
