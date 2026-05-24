"""Add external run observation fields.

Revision ID: 20260521173000
Revises: 20260514123000
Create Date: 2026-05-21 17:30:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260521173000"
down_revision = "20260514123000"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "runs",
        sa.Column(
            "source_kind",
            sa.Text(),
            nullable=False,
            server_default="playbook",
        ),
    )
    op.add_column("runs", sa.Column("display_title", sa.Text(), nullable=True))
    op.add_column(
        "runs",
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "workspace_run_feed",
        sa.Column(
            "source_kind",
            sa.Text(),
            nullable=False,
            server_default="playbook",
        ),
    )
    op.add_column(
        "workspace_run_feed",
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_runs_workspace_source_status_updated
            ON runs (workspace_id, source_kind, status, updated_at DESC)
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_workspace_run_feed_source_time
            ON workspace_run_feed (workspace_id, source_kind, occurred_at DESC, feed_id)
            """
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS idx_workspace_run_feed_source_time"
        )
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS idx_runs_workspace_source_status_updated"
        )

    op.drop_column("workspace_run_feed", "payload")
    op.drop_column("workspace_run_feed", "source_kind")
    op.drop_column("runs", "heartbeat_at")
    op.drop_column("runs", "display_title")
    op.drop_column("runs", "source_kind")
