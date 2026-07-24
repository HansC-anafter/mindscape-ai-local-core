"""Add the runtime queue projection read-budget index.

Revision ID: 20260715023000
Revises: None (independent Local Core read-budget branch)
Create Date: 2026-07-15 02:30:00.000000
"""

from alembic import op
from sqlalchemy import text


revision = "20260715023000"
down_revision = None
branch_labels = ("local_core_runtime_read_budget",)
depends_on = None


INDEX_NAME = "idx_tsp_queue_ready_eligible_v1"
OBSOLETE_TASKS_INDEX_NAME = "idx_tasks_queue_ready_eligible_v1"


def upgrade() -> None:
    required_projection_columns_ready = op.get_bind().execute(
        text(
            """
            SELECT COUNT(*) = 7
            FROM pg_attribute
            WHERE attrelid = to_regclass('public.task_summary_projection')
              AND attname IN (
                  'queue_shard',
                  'next_eligible_at',
                  'task_id',
                  'status',
                  'task_type',
                  'frontier_state',
                  'blocked_reason'
              )
              AND attnum > 0
              AND NOT attisdropped
            """
        )
    ).scalar()
    if required_projection_columns_ready is not True:
        raise RuntimeError(
            "task_summary_projection is missing required runtime queue columns"
        )

    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '900s'")
        try:
            op.execute(
                f"""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME}
                ON task_summary_projection (
                    queue_shard,
                    next_eligible_at,
                    task_id
                )
                WHERE status = 'pending'
                  AND task_type IN ('playbook_execution', 'tool_execution')
                  AND frontier_state = 'ready'
                  AND next_eligible_at IS NOT NULL
                  AND (blocked_reason IS NULL OR blocked_reason = '')
                """
            )
            authoritative_index_ready = op.get_bind().execute(
                text(
                    """
                    SELECT COALESCE(bool_and(i.indisvalid AND i.indisready), FALSE)
                    FROM pg_index AS i
                    JOIN pg_class AS c ON c.oid = i.indexrelid
                    JOIN pg_namespace AS n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'public'
                      AND c.relname = :index_name
                    """
                ),
                {"index_name": INDEX_NAME},
            ).scalar()
            if authoritative_index_ready is not True:
                raise RuntimeError(
                    f"authoritative queue projection index is not valid/ready: {INDEX_NAME}"
                )
            op.execute(
                f"DROP INDEX CONCURRENTLY IF EXISTS {OBSOLETE_TASKS_INDEX_NAME}"
            )
        finally:
            op.execute("RESET statement_timeout")
            op.execute("RESET lock_timeout")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '120s'")
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME}")
        op.execute("RESET statement_timeout")
        op.execute("RESET lock_timeout")
