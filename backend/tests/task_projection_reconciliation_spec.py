from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from backend.app.services import task_projection_reconciliation as reconciliation
from backend.app.services.task_projection_builder import TaskProjectionBuilder
from backend.scripts import backfill_task_summary_projection


class _Result:
    def __init__(self, *, rows=None, rowcount=0):
        self._rows = list(rows or [])
        self.rowcount = rowcount

    def mappings(self):
        return self

    def all(self):
        return list(self._rows)


class _Connection:
    def __init__(self, drift_batches):
        self.dialect = SimpleNamespace(name="postgresql")
        self.drift_batches = list(drift_batches)
        self.calls = []

    def execute(self, statement, params=None):
        source = str(statement)
        self.calls.append((source, dict(params or {})))
        if "active_task_truth_drift" in source or "active_projection_queue_drift" in source:
            return _Result(rows=self.drift_batches.pop(0))
        if "DELETE FROM task_summary_projection" in source:
            return _Result(rowcount=len((params or {}).get("task_ids") or []))
        if "set_config" in source:
            return _Result()
        raise AssertionError(f"unexpected SQL: {source}")


class _Builder(TaskProjectionBuilder):
    def __init__(self, connection):
        self.connection = connection
        self.upserted = []

    @contextmanager
    def get_connection(self):
        yield self.connection

    @contextmanager
    def transaction(self):
        yield self.connection

    def upsert_task_summary_from_task_id(self, task_id, *, conn=None, **_kwargs):
        assert conn is self.connection
        self.upserted.append(task_id)
        return True


def test_active_projection_reconciliation_dry_run_is_bounded_and_read_only():
    connection = _Connection(
        [
            [{"task_id": "stale-task", "task_exists": True}],
            [{"task_id": "orphan-task", "task_exists": False}],
        ]
    )
    builder = _Builder(connection)

    result = builder.reconcile_active_task_summary_projection(limit=1000)

    assert result == {
        "mode": "dry_run",
        "limit": 1000,
        "examined": 2,
        "existing_task_drift": 1,
        "orphan_projection_drift": 1,
        "truncated": False,
        "upserted": 0,
        "deleted_orphans": 0,
        "post_check_drift": 2,
        "post_check_truncated": False,
    }
    assert builder.upserted == []
    assert not any("DELETE FROM task_summary_projection" in sql for sql, _ in connection.calls)
    assert any(params.get("candidate_limit") == 1001 for _, params in connection.calls)


def test_active_projection_reconciliation_applies_existing_and_orphan_repairs_once():
    connection = _Connection(
        [
            [
                {"task_id": "stale-task", "task_exists": True},
                {"task_id": "missing-projection", "task_exists": True},
            ],
            [{"task_id": "orphan-task", "task_exists": False}],
            [],
            [],
        ]
    )
    builder = _Builder(connection)

    result = builder.reconcile_active_task_summary_projection(
        limit=1000,
        apply=True,
    )

    assert result["mode"] == "apply"
    assert result["upserted"] == 2
    assert result["deleted_orphans"] == 1
    assert result["post_check_drift"] == 0
    assert result["post_check_truncated"] is False
    assert builder.upserted == ["missing-projection", "stale-task"]
    delete_calls = [
        params
        for sql, params in connection.calls
        if "DELETE FROM task_summary_projection" in sql
    ]
    assert delete_calls == [{"task_ids": ["orphan-task"]}]
    delete_source = next(
        sql
        for sql, _ in connection.calls
        if "DELETE FROM task_summary_projection" in sql
    )
    assert "NOT EXISTS" in delete_source
    assert "tasks.id::text = projection.task_id" in delete_source


def test_active_projection_reconciliation_caps_each_batch_at_one_thousand():
    rows = [
        {"task_id": f"task-{index:04d}", "task_exists": True}
        for index in range(1001)
    ]
    connection = _Connection([rows, []])
    builder = _Builder(connection)

    result = builder.reconcile_active_task_summary_projection(limit=5000)

    assert result["limit"] == 1000
    assert result["examined"] == 1000
    assert result["truncated"] is True
    assert builder.upserted == []


def test_active_projection_drift_query_uses_only_control_fields_and_active_ids():
    task_source = str(reconciliation._ACTIVE_TASK_TRUTH_DRIFT_SQL)
    projection_source = str(reconciliation._ACTIVE_PROJECTION_QUEUE_DRIFT_SQL)
    source = task_source + projection_source

    assert "tasks.status = 'running'" in task_source
    assert "tasks.status = 'pending'" in task_source
    assert "projection.status = 'pending'" in projection_source
    assert "projection.next_eligible_at IS NOT NULL" in projection_source
    assert "tasks.id::text" in source
    assert "projection.task_id" in source
    assert "IS DISTINCT FROM" in source
    assert "tasks.params" not in source
    assert "tasks.result" not in source
    assert "tasks.execution_context" not in source
    assert "LIMIT :candidate_limit" in source


def test_backfill_script_routes_active_reconciliation_without_full_count(monkeypatch, capsys):
    calls = []

    class _ScriptBuilder:
        def reconcile_active_task_summary_projection(self, **kwargs):
            calls.append(kwargs)
            return {"mode": "dry_run", "post_check_drift": 0}

    monkeypatch.setattr(
        backfill_task_summary_projection,
        "TaskProjectionBuilder",
        _ScriptBuilder,
    )

    assert backfill_task_summary_projection.main(
        ["--reconcile-active", "--limit", "25"]
    ) == 0
    assert calls == [{"limit": 25, "apply": False}]
    output = capsys.readouterr().out
    assert '"ok": true' in output
    assert '"mode": "dry_run"' in output


def test_backfill_script_clamps_explicit_zero_limit_in_builder(monkeypatch):
    calls = []

    class _ScriptBuilder:
        def reconcile_active_task_summary_projection(self, **kwargs):
            calls.append(kwargs)
            return {"mode": "dry_run", "post_check_drift": 0}

    monkeypatch.setattr(
        backfill_task_summary_projection,
        "TaskProjectionBuilder",
        _ScriptBuilder,
    )

    assert backfill_task_summary_projection.main(
        ["--reconcile-active", "--limit", "0"]
    ) == 0
    assert calls == [{"limit": 0, "apply": False}]


def test_backfill_script_returns_structured_failure_for_reconcile_error(monkeypatch, capsys):
    class _ScriptBuilder:
        def reconcile_active_task_summary_projection(self, **_kwargs):
            raise RuntimeError("query failed")

    monkeypatch.setattr(
        backfill_task_summary_projection,
        "TaskProjectionBuilder",
        _ScriptBuilder,
    )

    assert backfill_task_summary_projection.main(["--reconcile-active"]) == 2
    output = capsys.readouterr().out
    assert '"ok": false' in output
    assert '"error_code": "active_projection_reconciliation_failed"' in output
    assert '"error_type": "RuntimeError"' in output


def test_backfill_script_rejects_apply_outside_active_reconciliation():
    with pytest.raises(SystemExit, match="--apply requires --reconcile-active"):
        backfill_task_summary_projection.main(["--apply"])
