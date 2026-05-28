"""Create runner queue capacity snapshots

Revision ID: 20260528120000
Revises: 20260508033000
Create Date: 2026-05-28 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260528120000"
down_revision = "20260508033000"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "runner_queue_capacity_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("queue_shard", sa.Text(), nullable=False),
        sa.Column("pending_depth", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processing_depth", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("delayed_depth", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deadletter_depth", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("visible_lane_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "visible_lanes_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("active_runner_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_inflight_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inflight_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_slots_total", sa.Integer(), nullable=False, server_default="0"),
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_runner_queue_capacity_snapshots_latest
        ON runner_queue_capacity_snapshots (queue_shard, captured_at DESC)
        """
    )


def downgrade():
    op.drop_index(
        "idx_runner_queue_capacity_snapshots_latest",
        table_name="runner_queue_capacity_snapshots",
    )
    op.drop_table("runner_queue_capacity_snapshots")
