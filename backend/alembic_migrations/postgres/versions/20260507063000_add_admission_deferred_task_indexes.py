"""Add indexes for admission-deferred task release scans

Revision ID: 20260507063000
Revises: 20260430000000
Create Date: 2026-05-07 06:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260507063000"
down_revision = "20260430000000"
branch_labels = None
depends_on = None


INDEXES = [
    (
        "idx_tasks_admission_deferred_due",
        """
        ON tasks (next_eligible_at, created_at, id)
        WHERE status = 'pending'
          AND blocked_reason = 'admission_deferred'
          AND task_type IN ('playbook_execution', 'tool_execution')
        """,
    ),
    (
        "idx_tasks_admission_deferred_due_shard",
        """
        ON tasks (queue_shard, next_eligible_at, created_at, id)
        WHERE status = 'pending'
          AND blocked_reason = 'admission_deferred'
          AND task_type IN ('playbook_execution', 'tool_execution')
        """,
    ),
    (
        "idx_tasks_admission_deferred_release_order",
        """
        ON tasks (
          queue_shard,
          (
            CASE
              WHEN COALESCE(execution_context->'admission_policy'->>'visibility', '') = 'visible' THEN 0
              WHEN COALESCE(execution_context->'admission'->>'visibility', '') = 'visible' THEN 0
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
        "idx_tasks_admission_deferred_release_order_global",
        """
        ON tasks (
          (
            CASE
              WHEN COALESCE(execution_context->'admission_policy'->>'visibility', '') = 'visible' THEN 0
              WHEN COALESCE(execution_context->'admission'->>'visibility', '') = 'visible' THEN 0
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
        "idx_tasks_admission_deferred_release_order_browser",
        """
        ON tasks (
          (
            CASE
              WHEN COALESCE(execution_context->'admission_policy'->>'visibility', '') = 'visible' THEN 0
              WHEN COALESCE(execution_context->'admission'->>'visibility', '') = 'visible' THEN 0
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
        "idx_tasks_admission_deferred_release_order_default",
        """
        ON tasks (
          (
            CASE
              WHEN COALESCE(execution_context->'admission_policy'->>'visibility', '') = 'visible' THEN 0
              WHEN COALESCE(execution_context->'admission'->>'visibility', '') = 'visible' THEN 0
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
        "idx_tasks_admission_deferred_release_order_vision",
        """
        ON tasks (
          (
            CASE
              WHEN COALESCE(execution_context->'admission_policy'->>'visibility', '') = 'visible' THEN 0
              WHEN COALESCE(execution_context->'admission'->>'visibility', '') = 'visible' THEN 0
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
    (
        "idx_tasks_pending_agent_dispatch_workspace_created",
        """
        ON tasks (workspace_id, created_at DESC, id DESC)
        WHERE status = 'pending'
          AND task_type = 'agent_dispatch'
        """,
    ),
]


def upgrade():
    conn = op.get_bind()
    for index_name, index_body in INDEXES:
        conn.execute(sa.text(f"CREATE INDEX IF NOT EXISTS {index_name} {index_body}"))


def downgrade():
    conn = op.get_bind()
    for index_name, _ in reversed(INDEXES):
        conn.execute(sa.text(f"DROP INDEX IF EXISTS {index_name}"))
