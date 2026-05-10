"""Add indexes for cold task release scans.

Revision ID: 20260510023000
Revises: 20260509164000
Create Date: 2026-05-10 02:30:00.000000
"""

from alembic import op


revision = "20260510023000"
down_revision = "20260509164000"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tasks_cold_blocked_due_shard
            ON tasks (queue_shard, blocked_reason, next_eligible_at, created_at, id)
            INCLUDE (pack_id)
            WHERE status = 'pending'
              AND frontier_state = 'cold'
              AND blocked_reason IN ('concurrency_locked', 'dependency_hold')
              AND task_type IN ('playbook_execution', 'tool_execution')
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tasks_cold_blocked_pack_due_shard
            ON tasks (queue_shard, blocked_reason, pack_id, next_eligible_at, created_at, id)
            WHERE status = 'pending'
              AND frontier_state = 'cold'
              AND blocked_reason IN ('concurrency_locked', 'dependency_hold')
              AND task_type IN ('playbook_execution', 'tool_execution')
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tasks_cold_unblocked_pack_due_shard
            ON tasks (queue_shard, pack_id, next_eligible_at, created_at, id)
            WHERE status = 'pending'
              AND frontier_state = 'cold'
              AND (blocked_reason IS NULL OR blocked_reason = '')
              AND task_type IN ('playbook_execution', 'tool_execution')
            """
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS idx_tasks_cold_unblocked_pack_due_shard"
        )
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS idx_tasks_cold_blocked_pack_due_shard"
        )
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_tasks_cold_blocked_due_shard")
