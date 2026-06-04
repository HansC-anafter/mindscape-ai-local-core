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


def test_workspace_executions_route_uses_projection_store_only():
    route_source = (
        _backend_root() / "app/routes/core/workspace/tasks.py"
    ).read_text(encoding="utf-8")
    route_source = route_source.split(
        "async def get_workspace_executions",
        maxsplit=1,
    )[1].split("def _load_execution_progress_snapshot_payload", maxsplit=1)[0]

    assert "WorkspaceExecutionActivityStore()" in route_source
    assert "list_executions" in route_source
    assert "FROM tasks" not in route_source
    assert "TasksStore()" not in route_source
    assert "list_executions_by_workspace" not in route_source

    feature_route_source = (
        _backend_root() / "features/workspace/executions.py"
    ).read_text(encoding="utf-8")
    feature_list_source = feature_route_source.split(
        "async def list_executions",
        maxsplit=1,
    )[1].split("@router.get", maxsplit=1)[0]
    assert "WorkspaceExecutionActivityStore()" in feature_list_source
    assert "list_executions_payload(" not in feature_list_source
    assert "TasksStore(" not in feature_list_source


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


def test_workspace_execution_activity_service_uses_projection_only():
    service_source = (
        _backend_root()
        / "app/services/workspace_execution_activity.py"
    ).read_text(encoding="utf-8")

    assert "FROM task_summary_projection" in service_source
    assert "FROM tasks" not in service_source
    assert "status IN :statuses" in service_source
    assert "parent_execution_id = :parent_execution_id" in service_source
    assert "CASE LOWER(status)" in service_source


def test_workspace_execution_activity_post_detail_hydration_is_bounded():
    service_source = (
        _backend_root()
        / "app/services/workspace_execution_activity.py"
    ).read_text(encoding="utf-8")
    hydration_source = (
        _backend_root()
        / "app/services/workspace_execution_input_hydration.py"
    ).read_text(encoding="utf-8")

    assert "hydrate_missing_execution_inputs" in service_source
    assert "ig_pin_post_detail" in hydration_source
    assert "FROM tasks" in hydration_source
    assert "WHERE id IN :task_ids" in hydration_source
    assert "pack_id = :pack_id" in hydration_source
    assert "shortcodes" in hydration_source
    assert "tags" in hydration_source


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


def test_projection_execution_route_indexes_are_nonblocking_and_reversible():
    migration_source = (
        _backend_root()
        / "alembic_migrations/postgres/versions/"
        "20260514120000_add_task_summary_projection_execution_route_indexes.py"
    ).read_text(encoding="utf-8")

    assert "CREATE INDEX CONCURRENTLY IF NOT EXISTS" in migration_source
    assert "DROP INDEX CONCURRENTLY IF EXISTS" in migration_source
    assert "idx_task_summary_projection_parent_created" in migration_source
    assert "idx_task_summary_projection_pack_created" in migration_source


def test_active_execution_projection_index_is_nonblocking_and_ready_scoped():
    migration_source = (
        _backend_root()
        / "alembic_migrations/postgres/versions/"
        "20260529124000_add_task_summary_projection_active_execution_index.py"
    ).read_text(encoding="utf-8")
    service_source = (
        _backend_root() / "app/services/workspace_execution_activity.py"
    ).read_text(encoding="utf-8")

    assert "CREATE INDEX CONCURRENTLY IF NOT EXISTS" in migration_source
    assert "DROP INDEX CONCURRENTLY IF EXISTS" in migration_source
    assert "idx_task_summary_projection_active_status_pack_updated" in migration_source
    assert "frontier_state IN ('ready', 'running')" in migration_source
    assert "frontier_state IN ('ready', 'running')" in service_source


def test_projection_compact_inputs_are_schema_managed():
    migration_source = (
        _backend_root()
        / "alembic_migrations/postgres/versions/"
        "20260529123000_add_task_summary_projection_compact_inputs.py"
    ).read_text(encoding="utf-8")
    projection_builder_source = (
        _backend_root()
        / "app/services/task_projection_builder.py"
    ).read_text(encoding="utf-8")

    assert "compact_inputs" in migration_source
    assert "task_summary_projection" in migration_source
    assert "compact_inputs" in projection_builder_source
    assert "tasks.params::jsonb" in projection_builder_source
    assert "'shortcodes'" in projection_builder_source
    assert "'tags'" in projection_builder_source
