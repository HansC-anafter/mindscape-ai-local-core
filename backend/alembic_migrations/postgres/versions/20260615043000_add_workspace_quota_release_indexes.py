"""Add workspace quota release and reservation indexes for tasks.

Revision ID: 20260615043000
Revises: 20260614230000
Create Date: 2026-06-15 04:30:00.000000
"""

from alembic import op


revision = "20260615043000"
down_revision = "20260614230000"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tasks_cold_workspace_quota_due_shard
            ON tasks (queue_shard, next_eligible_at, created_at, id)
            INCLUDE (workspace_id, pack_id, blocked_reason)
            WHERE status = 'pending'
              AND frontier_state = 'cold'
              AND blocked_reason IN (
                    'workspace_allocation_quota_exhausted',
                    'workspace_allocation_required',
                    'workspace_allocation_disabled'
                  )
              AND task_type IN ('playbook_execution', 'tool_execution')
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tasks_ready_running_ws_reserved
            ON tasks (workspace_id, queue_shard, id)
            INCLUDE (pack_id, task_type, blocked_reason)
            WHERE status = 'running'
               OR (
                    status = 'pending'
                    AND frontier_state = 'ready'
                    AND (blocked_reason IS NULL OR blocked_reason = '')
                  )
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tasks_ready_running_ws_pack_selector
            ON tasks (workspace_id, queue_shard, pack_id, id)
            WHERE pack_id IS NOT NULL
              AND (
                    status = 'running'
                    OR (
                        status = 'pending'
                        AND frontier_state = 'ready'
                        AND (blocked_reason IS NULL OR blocked_reason = '')
                    )
                  )
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tasks_ready_running_ws_playbook_selector
            ON tasks (
                workspace_id,
                queue_shard,
                (execution_context->>'playbook_code'),
                id
            )
            WHERE execution_context->>'playbook_code' IS NOT NULL
              AND (
                    status = 'running'
                    OR (
                        status = 'pending'
                        AND frontier_state = 'ready'
                        AND (blocked_reason IS NULL OR blocked_reason = '')
                    )
                  )
            """
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS idx_tasks_ready_running_ws_playbook_selector"
        )
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS idx_tasks_ready_running_ws_pack_selector"
        )
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS idx_tasks_ready_running_ws_reserved"
        )
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS idx_tasks_cold_workspace_quota_due_shard"
        )
