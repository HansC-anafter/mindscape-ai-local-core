from pathlib import Path

from backend.app.services import queue_position_cache


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT
    / "backend"
    / "alembic_migrations"
    / "postgres"
    / "versions"
    / "20260715023000_add_runtime_task_read_budget_index.py"
)


def test_queue_position_queries_use_compact_projection():
    assert "FROM task_summary_projection" in queue_position_cache._QUEUE_TOTALS_SQL
    assert "FROM task_summary_projection" in queue_position_cache._QUEUE_POSITION_ESTIMATE_SQL
    assert "FROM tasks" not in queue_position_cache._QUEUE_TOTALS_SQL
    assert "FROM tasks" not in queue_position_cache._QUEUE_POSITION_ESTIMATE_SQL
    assert queue_position_cache.QUEUE_READ_STATEMENT_TIMEOUT_MS == 2_000


def test_queue_projection_index_matches_runtime_predicate():
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'revision = "20260715023000"' in source
    assert "down_revision = None" in source
    assert 'branch_labels = ("local_core_runtime_read_budget",)' in source
    assert "depends_on = None" in source
    assert "required_projection_columns_ready is not True" in source
    assert "task_summary_projection is missing required runtime queue columns" in source
    assert "CREATE INDEX CONCURRENTLY IF NOT EXISTS" in source
    assert "idx_tsp_queue_ready_eligible_v1" in source
    assert 'OBSOLETE_TASKS_INDEX_NAME = "idx_tasks_queue_ready_eligible_v1"' in source
    assert "authoritative_index_ready is not True" in source
    assert "ON tasks" not in source
    assert "ON task_summary_projection" in source
    assert "status = 'pending'" in source
    assert "task_type IN ('playbook_execution', 'tool_execution')" in source
    assert "frontier_state = 'ready'" in source
    assert "blocked_reason IS NULL OR blocked_reason = ''" in source
    assert "DROP INDEX CONCURRENTLY IF EXISTS" in source
    assert "DROP INDEX CONCURRENTLY IF EXISTS {OBSOLETE_TASKS_INDEX_NAME}" in source
    assert "SET lock_timeout = '5s'" in source


def test_queue_read_budget_is_applied_only_to_postgres_connections():
    calls: list[tuple[str, dict | None]] = []

    class PostgresDialect:
        name = "postgresql"

    class Connection:
        dialect = PostgresDialect()

        def execute(self, statement, params=None):
            calls.append((str(statement), params))

    queue_position_cache._apply_queue_read_budget(Connection())

    assert "set_config('statement_timeout'" in calls[0][0]
    assert calls[0][1] == {"statement_timeout": "2000ms"}
