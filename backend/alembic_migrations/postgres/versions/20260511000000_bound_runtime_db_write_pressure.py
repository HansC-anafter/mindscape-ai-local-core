"""Bound runtime database write pressure.

Revision ID: 20260511000000
Revises: 20260510023000
Create Date: 2026-05-11 00:00:00.000000
"""

from alembic import op


revision = "20260511000000"
down_revision = "20260510023000"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        ALTER TABLE tasks SET (
            autovacuum_vacuum_scale_factor = 0.02,
            autovacuum_vacuum_threshold = 500,
            autovacuum_analyze_scale_factor = 0.01,
            autovacuum_analyze_threshold = 500
        )
        """
    )
    op.execute(
        """
        ALTER TABLE artifacts SET (
            autovacuum_vacuum_scale_factor = 0.02,
            autovacuum_vacuum_threshold = 250,
            autovacuum_analyze_scale_factor = 0.01,
            autovacuum_analyze_threshold = 250
        )
        """
    )
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tasks_cold_unblocked_due_shard
            ON tasks (queue_shard, next_eligible_at, created_at, id)
            INCLUDE (pack_id)
            WHERE status = 'pending'
              AND frontier_state = 'cold'
              AND (blocked_reason IS NULL OR blocked_reason = '')
              AND task_type IN ('playbook_execution', 'tool_execution')
            """
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS idx_tasks_cold_unblocked_due_shard"
        )
    op.execute("ALTER TABLE artifacts RESET (autovacuum_vacuum_scale_factor)")
    op.execute("ALTER TABLE artifacts RESET (autovacuum_vacuum_threshold)")
    op.execute("ALTER TABLE artifacts RESET (autovacuum_analyze_scale_factor)")
    op.execute("ALTER TABLE artifacts RESET (autovacuum_analyze_threshold)")
    op.execute("ALTER TABLE tasks RESET (autovacuum_vacuum_scale_factor)")
    op.execute("ALTER TABLE tasks RESET (autovacuum_vacuum_threshold)")
    op.execute("ALTER TABLE tasks RESET (autovacuum_analyze_scale_factor)")
    op.execute("ALTER TABLE tasks RESET (autovacuum_analyze_threshold)")
