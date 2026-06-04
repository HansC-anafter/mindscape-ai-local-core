"""Create workspace host resource allocation ledger.

Revision ID: 20260604024130
Revises: 20260603010000
Create Date: 2026-06-04 02:41:30.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260604024130"
down_revision = "20260603010000"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "host_resource_workspace_allocations",
        sa.Column("allocation_id", sa.Text(), primary_key=True),
        sa.Column("workspace_id", sa.Text(), nullable=False),
        sa.Column("lane_id", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column(
            "max_worker_target",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "max_concurrency",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "state",
            sa.Text(),
            nullable=False,
            server_default="enabled",
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(
            ["lane_id"],
            ["host_resource_lanes.lane_id"],
            ondelete="CASCADE",
        ),
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_host_resource_workspace_allocations_workspace_lane
        ON host_resource_workspace_allocations (workspace_id, lane_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_host_resource_workspace_allocations_lane_state
        ON host_resource_workspace_allocations (lane_id, state)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_host_resource_workspace_allocations_workspace_state
        ON host_resource_workspace_allocations (workspace_id, state)
        """
    )


def downgrade():
    op.drop_index(
        "idx_host_resource_workspace_allocations_workspace_state",
        table_name="host_resource_workspace_allocations",
    )
    op.drop_index(
        "idx_host_resource_workspace_allocations_lane_state",
        table_name="host_resource_workspace_allocations",
    )
    op.drop_index(
        "uq_host_resource_workspace_allocations_workspace_lane",
        table_name="host_resource_workspace_allocations",
    )
    op.drop_table("host_resource_workspace_allocations")
