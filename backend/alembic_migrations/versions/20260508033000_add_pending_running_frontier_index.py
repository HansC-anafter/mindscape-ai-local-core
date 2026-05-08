"""Add index for stale pending running frontier scans

Revision ID: 20260508033000
Revises: 20260321190000
Create Date: 2026-05-08 03:30:00.000000
"""

from alembic import op


revision = "20260508033000"
down_revision = "20260321190000"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_tasks_frontier_running_pending
        ON tasks (started_at ASC NULLS LAST, created_at, id)
        WHERE status = 'pending'
          AND frontier_state = 'running'
          AND task_type IN ('playbook_execution', 'tool_execution')
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_tasks_pending_runner_ownership_cleanup
        ON tasks (queue_shard, next_eligible_at, created_at, id)
        WHERE status = 'pending'
          AND task_type IN ('playbook_execution', 'tool_execution')
          AND (
              (execution_context->>'runner_id') IS NOT NULL
              OR (execution_context->>'heartbeat_at') IS NOT NULL
              OR started_at IS NOT NULL
          )
        """
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_tasks_pending_runner_ownership_cleanup")
    op.execute("DROP INDEX IF EXISTS idx_tasks_frontier_running_pending")
