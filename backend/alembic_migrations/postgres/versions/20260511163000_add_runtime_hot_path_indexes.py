"""Add indexes for runtime hot read and release paths.

Revision ID: 20260511163000
Revises: 20260511050000
Create Date: 2026-05-11 16:30:00.000000
"""

from alembic import op


revision = "20260511163000"
down_revision = "20260511050000"
branch_labels = None
depends_on = None


INDEXES = [
    (
        "idx_workspaces_owner_updated_desc",
        """
        ON workspaces (owner_user_id, updated_at DESC, id)
        """,
    ),
    (
        "idx_character_cards_workspace_updated_desc",
        """
        ON character_cards (workspace_id, updated_at DESC, character_card_id)
        """,
    ),
    (
        "idx_tasks_cold_resource_wait_due_shard",
        """
        ON tasks (queue_shard, next_eligible_at, created_at, id)
        INCLUDE (pack_id)
        WHERE status = 'pending'
          AND frontier_state = 'cold'
          AND blocked_reason = 'resource_wait'
          AND task_type IN ('playbook_execution', 'tool_execution')
        """,
    ),
    (
        "idx_tasks_cold_resource_wait_due_global",
        """
        ON tasks (next_eligible_at, created_at, id)
        INCLUDE (pack_id, queue_shard)
        WHERE status = 'pending'
          AND frontier_state = 'cold'
          AND blocked_reason = 'resource_wait'
          AND task_type IN ('playbook_execution', 'tool_execution')
        """,
    ),
    (
        "idx_tasks_cold_blocked_due_default",
        """
        ON tasks (blocked_reason, next_eligible_at, created_at, id)
        INCLUDE (pack_id, queue_shard)
        WHERE status = 'pending'
          AND frontier_state = 'cold'
          AND blocked_reason IN ('concurrency_locked', 'dependency_hold')
          AND task_type IN ('playbook_execution', 'tool_execution')
          AND (
            queue_shard IN ('default_local', 'default')
            OR queue_shard IS NULL
          )
        """,
    ),
    (
        "idx_tasks_cold_unblocked_due_default",
        """
        ON tasks (next_eligible_at, created_at, id)
        INCLUDE (pack_id, queue_shard)
        WHERE status = 'pending'
          AND frontier_state = 'cold'
          AND (blocked_reason IS NULL OR blocked_reason = '')
          AND task_type IN ('playbook_execution', 'tool_execution')
          AND (
            queue_shard IN ('default_local', 'default')
            OR queue_shard IS NULL
          )
        """,
    ),
]


def upgrade():
    with op.get_context().autocommit_block():
        for index_name, ddl in INDEXES:
            op.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {index_name} {ddl}")


def downgrade():
    with op.get_context().autocommit_block():
        for index_name, _ddl in reversed(INDEXES):
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {index_name}")
