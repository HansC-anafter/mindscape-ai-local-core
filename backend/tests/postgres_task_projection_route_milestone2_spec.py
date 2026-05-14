from pathlib import Path


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_workspace_tasks_route_uses_projection_store_only():
    route_source = (
        _backend_root() / "app/routes/core/workspace/tasks.py"
    ).read_text(encoding="utf-8")
    loader_source = route_source.split(
        "async def _load_workspace_tasks_payload",
        maxsplit=1,
    )[1].split("@router.get", maxsplit=1)[0]

    assert "TasksProjectionStore()" in loader_source
    assert "list_workspace_tasks" in loader_source
    assert "TasksStore()" not in loader_source
    assert "list_executions_by_workspace" not in loader_source
    assert "list_tasks_by_workspace" not in loader_source


def test_projection_store_reads_projection_table_not_task_payload_columns():
    store_source = (
        _backend_root()
        / "app/services/stores/postgres/task_projection_store.py"
    ).read_text(encoding="utf-8")

    assert "FROM task_summary_projection" in store_source
    assert "FROM tasks" not in store_source
    assert "tasks.params" not in store_source
    assert "tasks.result" not in store_source
    assert "tasks.execution_context" not in store_source
    assert "tasks.blocked_payload" not in store_source
    assert "next_eligible_at" in store_source
    assert "blocked_reason" in store_source
    assert "frontier_state" in store_source


def test_projection_read_indexes_are_nonblocking_and_reversible():
    migration_source = (
        _backend_root()
        / "alembic_migrations/postgres/versions/"
        "20260514113000_add_task_summary_projection_read_indexes.py"
    ).read_text(encoding="utf-8")

    assert "CREATE INDEX CONCURRENTLY IF NOT EXISTS" in migration_source
    assert "DROP INDEX CONCURRENTLY IF EXISTS" in migration_source
    assert "idx_task_summary_projection_exec_created" in migration_source
    assert "idx_task_summary_projection_include_order" in migration_source
    assert "idx_task_summary_projection_ready_order" in migration_source


def test_projection_control_fields_are_schema_managed():
    migration_source = (
        _backend_root()
        / "alembic_migrations/postgres/versions/"
        "20260514114500_add_task_summary_projection_control_fields.py"
    ).read_text(encoding="utf-8")

    assert "next_eligible_at" in migration_source
    assert "blocked_reason" in migration_source
    assert "frontier_state" in migration_source
    assert "frontier_enqueued_at" in migration_source
    assert "blocked_payload" not in migration_source
