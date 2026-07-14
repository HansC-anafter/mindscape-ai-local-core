"""Add the runtime queue projection read-budget index.

Revision ID: 20260715010000
Revises: 20260622193000
Create Date: 2026-07-15 01:00:00.000000
"""

from alembic import op


revision = "20260715010000"
down_revision = "20260622193000"
branch_labels = None
depends_on = None


TASKS_INDEX_NAME = "idx_tasks_queue_ready_eligible_v1"
PROJECTION_INDEX_NAME = "idx_tsp_queue_ready_eligible_v1"


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '120s'")
        op.execute("SET statement_timeout = '900s'")
        op.execute(
            f"""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS {TASKS_INDEX_NAME}
            ON tasks (
                queue_shard,
                next_eligible_at,
                id
            )
            WHERE status = 'pending'
              AND task_type IN ('playbook_execution', 'tool_execution')
              AND frontier_state = 'ready'
              AND next_eligible_at IS NOT NULL
              AND (blocked_reason IS NULL OR blocked_reason = '')
            """
        )
        op.execute(
            f"""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS {PROJECTION_INDEX_NAME}
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
        op.execute("RESET statement_timeout")
        op.execute("RESET lock_timeout")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '120s'")
        op.execute("SET statement_timeout = '120s'")
        op.execute(
            f"DROP INDEX CONCURRENTLY IF EXISTS {PROJECTION_INDEX_NAME}"
        )
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {TASKS_INDEX_NAME}")
        op.execute("RESET statement_timeout")
        op.execute("RESET lock_timeout")
