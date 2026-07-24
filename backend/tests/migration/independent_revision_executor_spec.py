from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from backend.app.services.migrations import independent_revision_executor as executor


class _Result:
    def __init__(self, value=None):
        self.value = value

    def scalar(self):
        return self.value


class _Connection:
    def __init__(self, *, already_applied: bool = False):
        self.already_applied = already_applied
        self.recorded = already_applied
        self.calls = []

    def execute(self, statement, parameters=None):
        sql = str(statement)
        self.calls.append((sql, parameters))
        if sql.startswith("SELECT EXISTS"):
            return _Result(self.recorded)
        if sql.startswith("INSERT INTO alembic_version"):
            self.recorded = True
        return _Result()


class _Engine:
    def __init__(self, connection: _Connection):
        self.connection = connection
        self.disposed = False

    @contextmanager
    def begin(self):
        yield self.connection

    def dispose(self):
        self.disposed = True


def _revision(events, *, down_revision=None):
    return SimpleNamespace(
        revision="20260716020000",
        down_revision=down_revision,
        branch_labels=("capability_pack_install_atomicity",),
        module=SimpleNamespace(upgrade=lambda: events.append("upgrade")),
    )


def test_independent_revision_executes_upgrade_and_receipt_in_one_engine_scope(
    monkeypatch,
) -> None:
    events = []
    connection = _Connection()
    engine = _Engine(connection)
    monkeypatch.setattr(
        executor,
        "create_session_semantics_engine",
        lambda _url, _name: engine,
    )
    monkeypatch.setattr(
        executor.MigrationContext,
        "configure",
        lambda _connection, opts: ("context", opts),
    )

    @contextmanager
    def _operations_context(_context):
        yield

    monkeypatch.setattr(executor.Operations, "context", _operations_context)

    result = executor.execute_independent_revision(
        revision_script=_revision(events),
        postgres_url="postgresql://example",
        revision="20260716020000",
    )

    assert result is True
    assert events == ["upgrade"]
    assert connection.recorded is True
    assert any(
        sql.startswith("INSERT INTO alembic_version")
        for sql, _parameters in connection.calls
    )
    assert engine.disposed is True


def test_independent_revision_is_idempotent_when_receipt_exists(monkeypatch) -> None:
    events = []
    connection = _Connection(already_applied=True)
    engine = _Engine(connection)
    monkeypatch.setattr(
        executor,
        "create_session_semantics_engine",
        lambda _url, _name: engine,
    )

    result = executor.execute_independent_revision(
        revision_script=_revision(events),
        postgres_url="postgresql://example",
        revision="20260716020000",
    )

    assert result is True
    assert events == []
    assert not any(
        sql.startswith("INSERT INTO alembic_version")
        for sql, _parameters in connection.calls
    )


def test_independent_revision_rejects_revision_with_parent() -> None:
    with pytest.raises(ValueError, match="requires_base_parent"):
        executor.execute_independent_revision(
            revision_script=_revision([], down_revision="20260715010000"),
            postgres_url="postgresql://example",
            revision="20260716020000",
        )
