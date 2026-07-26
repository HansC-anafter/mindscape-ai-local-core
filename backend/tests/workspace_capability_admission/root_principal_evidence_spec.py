from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from backend.app.services.workspace_capability_admission.contracts import (
    RootPrincipalEvidence,
)
from backend.app.services.workspace_product_configuration.repository import (
    WorkspaceProductConfigurationRepository,
)


def test_root_principal_evidence_is_transient_and_frozen():
    evidence = RootPrincipalEvidence(
        workspace_id="workspace-a",
        actor_user_id="owner-a",
        allowed_workspace_ids=("workspace-a",),
        allowed_group_ids=(),
        workspace_owner_user_id="owner-a",
        group_owner_user_id=None,
    )

    with pytest.raises(FrozenInstanceError):
        evidence.actor_user_id = "attacker"


def test_root_aggregate_read_projects_owner_in_the_same_statement():
    row = SimpleNamespace(
        workspace_owner_user_id="owner-a",
        artifact_hash="a" * 64,
        catalog_hash="b" * 64,
        source_commit="commit-a",
        compiler_version="1",
        artifact_json={},
        readiness={},
        scopes=[],
    )

    class Connection:
        def __init__(self):
            self.calls = []

        def execute(self, statement, params):
            self.calls.append((str(statement), params))
            return SimpleNamespace(fetchone=lambda: row)

    connection = Connection()
    repository = object.__new__(
        WorkspaceProductConfigurationRepository
    )

    @contextmanager
    def connection_scope():
        yield connection

    repository.get_connection = connection_scope
    state = repository.load_effective_state(
        workspace_id="workspace-a",
        group_id=None,
    )

    assert len(connection.calls) == 1
    assert "owner_user_id" in connection.calls[0][0]
    assert state["workspace_owner_user_id"] == "owner-a"
