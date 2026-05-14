"""Add task event ledger, outbox, and projection tables.

Revision ID: 20260514103000
Revises: 20260514010000
Create Date: 2026-05-14 10:30:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260514103000"
down_revision = "20260514010000"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "runs",
        sa.Column("run_id", sa.Text(), primary_key=True),
        sa.Column("execution_id", sa.Text(), nullable=False),
        sa.Column("workspace_id", sa.Text(), nullable=False),
        sa.Column("task_id", sa.Text(), nullable=True),
        sa.Column("pack_id", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "schema_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_runs_workspace_created
        ON runs (workspace_id, created_at DESC)
        """
    )
    op.create_index("idx_runs_execution_id", "runs", ["execution_id"])

    op.create_table(
        "run_attempts",
        sa.Column("attempt_id", sa.Text(), primary_key=True),
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("task_id", sa.Text(), nullable=False),
        sa.Column("runner_id", sa.Text(), nullable=True),
        sa.Column(
            "attempt_no",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_run_attempts_idempotency_key",
        ),
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_run_attempts_run_created
        ON run_attempts (run_id, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_run_attempts_task_started
        ON run_attempts (task_id, started_at DESC)
        """
    )

    op.create_table(
        "task_events",
        sa.Column("event_id", sa.Text(), primary_key=True),
        sa.Column("task_id", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Text(), nullable=True),
        sa.Column("attempt_id", sa.Text(), nullable=True),
        sa.Column("workspace_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("from_status", sa.Text(), nullable=True),
        sa.Column("to_status", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_task_events_idempotency_key"),
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_task_events_task_time
        ON task_events (task_id, occurred_at DESC, event_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_task_events_workspace_time
        ON task_events (workspace_id, occurred_at DESC)
        """
    )

    op.create_table(
        "outbox_events",
        sa.Column("outbox_id", sa.Text(), primary_key=True),
        sa.Column("aggregate_type", sa.Text(), nullable=False),
        sa.Column("aggregate_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_outbox_events_idempotency_key"),
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_outbox_events_pending
        ON outbox_events (available_at, created_at, outbox_id)
        WHERE status = 'pending'
        """
    )

    op.create_table(
        "task_summary_projection",
        sa.Column("task_id", sa.Text(), primary_key=True),
        sa.Column("workspace_id", sa.Text(), nullable=False),
        sa.Column("execution_id", sa.Text(), nullable=True),
        sa.Column("parent_execution_id", sa.Text(), nullable=True),
        sa.Column("project_id", sa.Text(), nullable=True),
        sa.Column("pack_id", sa.Text(), nullable=True),
        sa.Column("task_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("queue_shard", sa.Text(), nullable=True),
        sa.Column(
            "priority",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("dedupe_key", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_event_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "schema_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_task_summary_projection_workspace_updated
        ON task_summary_projection (workspace_id, updated_at DESC, task_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_task_summary_projection_workspace_status
        ON task_summary_projection (workspace_id, status, updated_at DESC)
        """
    )

    op.create_table(
        "workspace_run_feed",
        sa.Column("feed_id", sa.Text(), primary_key=True),
        sa.Column("workspace_id", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("task_id", sa.Text(), nullable=True),
        sa.Column("execution_id", sa.Text(), nullable=True),
        sa.Column("pack_id", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "schema_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_workspace_run_feed_workspace_time
        ON workspace_run_feed (workspace_id, occurred_at DESC, feed_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_workspace_run_feed_run
        ON workspace_run_feed (run_id, occurred_at DESC)
        """
    )


def downgrade():
    op.drop_index("idx_workspace_run_feed_run", table_name="workspace_run_feed")
    op.drop_index(
        "idx_workspace_run_feed_workspace_time",
        table_name="workspace_run_feed",
    )
    op.drop_table("workspace_run_feed")

    op.drop_index(
        "idx_task_summary_projection_workspace_status",
        table_name="task_summary_projection",
    )
    op.drop_index(
        "idx_task_summary_projection_workspace_updated",
        table_name="task_summary_projection",
    )
    op.drop_table("task_summary_projection")

    op.drop_index("idx_outbox_events_pending", table_name="outbox_events")
    op.drop_table("outbox_events")

    op.drop_index("idx_task_events_workspace_time", table_name="task_events")
    op.drop_index("idx_task_events_task_time", table_name="task_events")
    op.drop_table("task_events")

    op.drop_index("idx_run_attempts_task_started", table_name="run_attempts")
    op.drop_index("idx_run_attempts_run_created", table_name="run_attempts")
    op.drop_table("run_attempts")

    op.drop_index("idx_runs_execution_id", table_name="runs")
    op.drop_index("idx_runs_workspace_created", table_name="runs")
    op.drop_table("runs")
