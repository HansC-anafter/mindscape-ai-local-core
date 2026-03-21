"""Add scheduler columns to tasks table for bounded queue frontier

Revision ID: 20260321083000
Revises: 20260320060000
Create Date: 2026-03-21 08:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260321083000"
down_revision = "20260320060000"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tasks",
        sa.Column(
            "next_eligible_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("NOW()"),
        ),
    )
    op.add_column("tasks", sa.Column("blocked_reason", sa.Text(), nullable=True))
    op.add_column("tasks", sa.Column("blocked_payload", sa.JSON(), nullable=True))
    op.add_column(
        "tasks",
        sa.Column(
            "queue_shard",
            sa.String(),
            nullable=True,
            server_default="default",
        ),
    )
    op.add_column("tasks", sa.Column("concurrency_key", sa.String(), nullable=True))
    op.add_column(
        "tasks",
        sa.Column(
            "frontier_state",
            sa.String(),
            nullable=True,
            server_default="cold",
        ),
    )
    op.add_column(
        "tasks",
        sa.Column("frontier_enqueued_at", sa.DateTime(timezone=True), nullable=True),
    )

    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE tasks
            SET next_eligible_at = COALESCE(
                    CAST(execution_context->>'resume_after' AS timestamptz),
                    created_at,
                    NOW()
                ),
                blocked_reason = CASE
                    WHEN execution_context->>'runner_skip_reason' IS NOT NULL
                        THEN execution_context->>'runner_skip_reason'
                    WHEN execution_context->>'dependency_hold' IS NOT NULL
                        THEN 'dependency_hold'
                    ELSE NULL
                END,
                blocked_payload = CASE
                    WHEN execution_context->>'dependency_hold' IS NOT NULL THEN
                        jsonb_build_object(
                            'dependency_hold',
                            execution_context->'dependency_hold'
                        )
                    ELSE blocked_payload
                END,
                queue_shard = CASE
                    WHEN pack_id = 'ig_analyze_pinned_reference' THEN 'ig_analysis'
                    WHEN pack_id IN ('ig_batch_pin_references', 'ig_analyze_following') THEN 'ig_browser'
                    ELSE 'default'
                END,
                frontier_state = CASE
                    WHEN status = 'running' THEN 'running'
                    WHEN status <> 'pending' THEN 'done'
                    WHEN COALESCE(
                        execution_context->>'runner_skip_reason',
                        CASE
                            WHEN execution_context->>'dependency_hold' IS NOT NULL THEN 'dependency_hold'
                            ELSE NULL
                        END
                    ) IS NOT NULL THEN 'cold'
                    WHEN COALESCE(
                        CAST(execution_context->>'resume_after' AS timestamptz),
                        created_at,
                        NOW()
                    ) > NOW() THEN 'cold'
                    WHEN task_type IN ('playbook_execution', 'tool_execution') THEN 'ready'
                    ELSE 'cold'
                END,
                frontier_enqueued_at = CASE
                    WHEN status = 'pending'
                         AND task_type IN ('playbook_execution', 'tool_execution')
                         AND COALESCE(
                                execution_context->>'runner_skip_reason',
                                CASE
                                    WHEN execution_context->>'dependency_hold' IS NOT NULL THEN 'dependency_hold'
                                    ELSE NULL
                                END
                             ) IS NULL
                         AND COALESCE(
                                CAST(execution_context->>'resume_after' AS timestamptz),
                                created_at,
                                NOW()
                             ) <= NOW()
                        THEN created_at
                    ELSE NULL
                END
            """
        )
    )

    op.alter_column("tasks", "next_eligible_at", nullable=False, server_default=None)
    op.alter_column("tasks", "queue_shard", nullable=False, server_default=None)
    op.alter_column("tasks", "frontier_state", nullable=False, server_default=None)

    op.create_index(
        "idx_tasks_frontier_cold",
        "tasks",
        ["queue_shard", "next_eligible_at", "created_at", "id"],
        unique=False,
        postgresql_where=sa.text(
            "status = 'pending' AND frontier_state = 'cold'"
        ),
    )
    op.create_index(
        "idx_tasks_frontier_ready",
        "tasks",
        ["queue_shard", "frontier_enqueued_at", "created_at", "id"],
        unique=False,
        postgresql_where=sa.text(
            "status = 'pending' AND frontier_state = 'ready'"
        ),
    )
    op.create_index(
        "idx_tasks_pending_concurrency_key",
        "tasks",
        ["concurrency_key", "created_at", "id"],
        unique=False,
        postgresql_where=sa.text(
            "status = 'pending' AND concurrency_key IS NOT NULL"
        ),
    )
    op.create_index(
        "idx_tasks_pending_queue_position",
        "tasks",
        ["queue_shard", "next_eligible_at", "created_at", "id"],
        unique=False,
        postgresql_where=sa.text(
            "status = 'pending' AND task_type IN ('playbook_execution', 'tool_execution')"
        ),
    )


def downgrade():
    op.drop_index("idx_tasks_pending_queue_position", table_name="tasks")
    op.drop_index("idx_tasks_pending_concurrency_key", table_name="tasks")
    op.drop_index("idx_tasks_frontier_ready", table_name="tasks")
    op.drop_index("idx_tasks_frontier_cold", table_name="tasks")
    op.drop_column("tasks", "frontier_enqueued_at")
    op.drop_column("tasks", "frontier_state")
    op.drop_column("tasks", "concurrency_key")
    op.drop_column("tasks", "queue_shard")
    op.drop_column("tasks", "blocked_payload")
    op.drop_column("tasks", "blocked_reason")
    op.drop_column("tasks", "next_eligible_at")
