from pathlib import Path


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_milestone1_migration_creates_single_path_control_plane_tables():
    migration = (
        _backend_root()
        / "alembic_migrations/postgres/versions/"
        / "20260514103000_add_task_events_outbox_and_projections.py"
    ).read_text(encoding="utf-8")

    assert 'revision = "20260514103000"' in migration
    assert 'down_revision = "20260514010000"' in migration
    for table_name in [
        "runs",
        "run_attempts",
        "task_events",
        "outbox_events",
        "task_summary_projection",
        "workspace_run_feed",
    ]:
        assert f'"{table_name}"' in migration
        assert f'op.drop_table("{table_name}")' in migration

    assert "uq_task_events_idempotency_key" in migration
    assert "uq_outbox_events_idempotency_key" in migration
    assert "uq_run_attempts_idempotency_key" in migration
    assert "VACUUM FULL" not in migration


def test_task_store_writes_events_attempts_and_projection_through_service_seams():
    tasks_base = (
        _backend_root() / "app/services/stores/tasks_store/_base.py"
    ).read_text(encoding="utf-8")
    tasks_runner = (
        _backend_root() / "app/services/stores/tasks_store/_runner.py"
    ).read_text(encoding="utf-8")

    assert "TaskEventsStore" in tasks_base
    assert "RunAttemptsStore" in tasks_base
    assert "TaskProjectionBuilder" in tasks_base
    assert "_record_task_control_event(" in tasks_base
    assert "_record_run_control_from_task(" in tasks_base
    assert "_record_latest_attempt_completion(" in tasks_base
    assert "_refresh_task_projection(" in tasks_base
    assert "_record_task_claim(" in tasks_runner
    assert "task_events" not in tasks_runner


def test_projection_builder_does_not_read_large_task_payload_columns():
    projection_builder = (
        _backend_root() / "app/services/task_projection_builder.py"
    ).read_text(encoding="utf-8")

    assert "task_summary_projection" in projection_builder
    assert "workspace_run_feed" in projection_builder
    assert "tasks.params" not in projection_builder
    assert "tasks.result" not in projection_builder
    assert "tasks.execution_context" not in projection_builder
    assert "tasks.blocked_payload" not in projection_builder
