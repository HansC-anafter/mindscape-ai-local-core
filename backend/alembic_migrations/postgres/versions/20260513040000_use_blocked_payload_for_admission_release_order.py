"""Use blocked_payload for admission-deferred release ordering.

Revision ID: 20260513040000
Revises: 20260513020000
Create Date: 2026-05-13 04:00:00.000000
"""

from alembic import op


revision = "20260513040000"
down_revision = "20260513020000"
branch_labels = None
depends_on = None


OLD_INDEXES = [
    "idx_tasks_admission_deferred_release_order",
    "idx_tasks_admission_deferred_release_order_global",
    "idx_tasks_admission_deferred_release_order_browser",
    "idx_tasks_admission_deferred_release_order_default",
    "idx_tasks_admission_deferred_release_order_vision",
]

NEW_INDEXES = [
    (
        "idx_tasks_admission_deferred_payload_release_order",
        """
        ON tasks (
          queue_shard,
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
        """,
    ),
    (
        "idx_tasks_admission_deferred_payload_release_global",
        """
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
        """,
    ),
    (
        "idx_tasks_admission_deferred_payload_release_browser",
        """
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
        """,
    ),
    (
        "idx_tasks_admission_deferred_payload_release_default",
        """
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
        """,
    ),
    (
        "idx_tasks_admission_deferred_payload_release_vision",
        """
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
        """,
    ),
]


def upgrade():
    with op.get_context().autocommit_block():
        for index_name, ddl in NEW_INDEXES:
            op.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {index_name} {ddl}")
        for index_name in OLD_INDEXES:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {index_name}")


def downgrade():
    with op.get_context().autocommit_block():
        for index_name, _ddl in reversed(NEW_INDEXES):
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {index_name}")
