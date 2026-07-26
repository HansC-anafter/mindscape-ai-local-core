from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from backend.app.services.host_runtime_bindings.contracts import (
    FinalizeBindingRetirementCommand,
    RequestBindingRetirementCommand,
)
from backend.app.services.host_runtime_bindings.lifecycle_repository import (
    HostRuntimeLifecycleRepositoryMixin,
)
from backend.app.services.host_runtime_bindings.state_machine import FINALIZER


class Result:
    def __init__(self, *, row=None, scalar=None):
        self.row = row
        self.scalar = scalar

    def fetchone(self):
        return self.row

    def scalar_one(self):
        return self.scalar


class Connection:
    def __init__(self, *, state: str, active_grants: int):
        self.state = state
        self.active_grants = active_grants
        self.updates: list[dict] = []

    def execute(self, statement, params):
        sql = str(statement)
        if "SELECT id, generation, desired_state" in sql:
            return Result(
                row=SimpleNamespace(
                    id=params["binding_id"],
                    generation=params["generation"],
                    desired_state=self.state,
                    finalizers=[FINALIZER],
                )
            )
        if "SELECT COUNT(*)" in sql:
            return Result(scalar=self.active_grants)
        if "UPDATE host_runtime_bindings" in sql:
            self.updates.append(dict(params))
            self.state = params["desired_state"]
            return Result()
        raise AssertionError(f"unexpected_sql:{sql}")


class Repository(HostRuntimeLifecycleRepositoryMixin):
    def __init__(self, connection: Connection):
        self.connection = connection
        self.receipts: list[dict] = []

    @contextmanager
    def transaction(self):
        yield self.connection

    @staticmethod
    def serialize_json(value):
        return value

    def _append_receipt(self, _conn, **payload):
        self.receipts.append(payload)


def test_retirement_request_keeps_finalizer_even_with_active_grants():
    connection = Connection(state="active", active_grants=2)
    repository = Repository(connection)

    repository.request_retirement(
        RequestBindingRetirementCommand(
            binding_id="binding-a",
            generation=3,
            reason="capability_upgrade",
        ),
        actor_id="operator-a",
    )

    assert connection.updates == [
        {
            "binding_id": "binding-a",
            "generation": 3,
            "desired_state": "retiring",
            "finalizers": [FINALIZER],
        }
    ]
    assert repository.receipts[0]["kind"] == "retiring"
    assert repository.receipts[0]["payload"]["active_grant_count"] == 2


def test_retirement_finalize_requires_zero_active_grants_and_clears_finalizer():
    blocked = Repository(Connection(state="retiring", active_grants=1))
    command = FinalizeBindingRetirementCommand(
        binding_id="binding-a",
        generation=3,
        supervisor_cleanup_terminal=True,
    )

    with pytest.raises(ValueError, match="active_grants"):
        blocked.finalize_retirement(command, actor_id="operator-a")
    assert blocked.connection.updates == []

    repository = Repository(Connection(state="retiring", active_grants=0))
    repository.finalize_retirement(command, actor_id="operator-a")

    assert repository.connection.updates[0]["desired_state"] == "retired"
    assert repository.connection.updates[0]["finalizers"] == []
    assert repository.receipts[0]["kind"] == "retired"
    assert repository.receipts[0]["payload"]["supervisor_cleanup_terminal"] is True
