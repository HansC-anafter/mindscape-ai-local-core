"""Drop redundant admission release indexes.

Revision ID: 20260513183000
Revises: 20260513040000
Create Date: 2026-05-13 18:30:00.000000
"""

from alembic import op


revision = "20260513183000"
down_revision = "20260513040000"
branch_labels = None
depends_on = None


DROP_INDEXES = [
    "idx_tasks_admission_deferred_payload_release_global",
    "idx_tasks_admission_deferred_payload_release_browser",
    "idx_tasks_admission_deferred_payload_release_default",
    "idx_tasks_admission_deferred_payload_release_vision",
]


def upgrade():
    with op.get_context().autocommit_block():
        for index_name in DROP_INDEXES:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {index_name}")


def downgrade():
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tasks_admission_deferred_payload_release_global
            ON tasks (
              (
                CASE
                  WHEN COALESCE(blocked_payload->>'visibility', '') = 'visible' THEN 0
                  ELSE 1
                END
              ),
              next_eligible_at,
              created_at,
              id
            )
            WHERE status = 'pending'
              AND blocked_reason = 'admission_deferred'
              AND task_type IN ('playbook_execution', 'tool_execution')
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tasks_admission_deferred_payload_release_browser
            ON tasks (
              (
                CASE
                  WHEN COALESCE(blocked_payload->>'visibility', '') = 'visible' THEN 0
                  ELSE 1
                END
              ),
              next_eligible_at,
              created_at,
              id
            )
            WHERE status = 'pending'
              AND blocked_reason = 'admission_deferred'
              AND task_type IN ('playbook_execution', 'tool_execution')
              AND queue_shard IN ('browser_local', 'ig_browser')
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tasks_admission_deferred_payload_release_default
            ON tasks (
              (
                CASE
                  WHEN COALESCE(blocked_payload->>'visibility', '') = 'visible' THEN 0
                  ELSE 1
                END
              ),
              next_eligible_at,
              created_at,
              id
            )
            WHERE status = 'pending'
              AND blocked_reason = 'admission_deferred'
              AND task_type IN ('playbook_execution', 'tool_execution')
              AND (
                queue_shard IN ('default_local', 'default')
                OR queue_shard IS NULL
              )
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tasks_admission_deferred_payload_release_vision
            ON tasks (
              (
                CASE
                  WHEN COALESCE(blocked_payload->>'visibility', '') = 'visible' THEN 0
                  ELSE 1
                END
              ),
              next_eligible_at,
              created_at,
              id
            )
            WHERE status = 'pending'
              AND blocked_reason = 'admission_deferred'
              AND task_type IN ('playbook_execution', 'tool_execution')
              AND queue_shard IN ('vision_local', 'ig_analysis')
            """
        )
