"""Add Resource Console backlog summary index.

Revision ID: 20260621023000
Revises: 20260615043000
Create Date: 2026-06-21 02:30:00.000000
"""

from alembic import op


revision = "20260621023000"
down_revision = "20260615043000"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tasks_resource_console_backlog_summary
            ON tasks (
                queue_shard,
                status,
                frontier_state,
                blocked_reason,
                pack_id
            )
            WHERE status IN ('pending', 'running')
              AND task_type IN ('playbook_execution', 'tool_execution')
              AND queue_shard IS NOT NULL
              AND queue_shard <> ''
            """
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS idx_tasks_resource_console_backlog_summary"
        )
