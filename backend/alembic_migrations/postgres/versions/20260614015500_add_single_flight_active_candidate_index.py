"""Add the single-flight active pending candidate index.

Revision ID: 20260614015500
Revises: 20260604173000
Create Date: 2026-06-14 01:55:00.000000
"""

from alembic import op


revision = "20260614015500"
down_revision = "20260604173000"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tasks_pending_active_concurrency_key
            ON tasks (concurrency_key, created_at, id)
            INCLUDE (status, frontier_state, next_eligible_at)
            WHERE status = 'pending'
              AND task_type IN ('playbook_execution', 'tool_execution')
              AND frontier_state IN ('ready', 'running')
              AND (blocked_reason IS NULL OR blocked_reason = '')
              AND concurrency_key IS NOT NULL
            """
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS idx_tasks_pending_active_concurrency_key"
        )
