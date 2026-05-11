"""Add global cold blocked due index.

Revision ID: 20260511030000
Revises: 20260511000000
Create Date: 2026-05-11 03:00:00.000000
"""

from alembic import op


revision = "20260511030000"
down_revision = "20260511000000"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tasks_cold_blocked_due_global
            ON tasks (blocked_reason, next_eligible_at, created_at, id)
            INCLUDE (pack_id, queue_shard)
            WHERE status = 'pending'
              AND frontier_state = 'cold'
              AND blocked_reason IN ('concurrency_locked', 'dependency_hold')
              AND task_type IN ('playbook_execution', 'tool_execution')
            """
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS idx_tasks_cold_blocked_due_global"
        )
