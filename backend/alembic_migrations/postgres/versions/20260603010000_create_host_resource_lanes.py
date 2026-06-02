"""Create dynamic host resource lanes.

Revision ID: 20260603010000
Revises: 20260529124000
Create Date: 2026-06-03 01:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260603010000"
down_revision = "20260529124000"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "host_resource_lanes",
        sa.Column("lane_id", sa.Text(), primary_key=True),
        sa.Column("workspace_id", sa.Text(), nullable=True),
        sa.Column("capability_scope", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("queue_shard", sa.Text(), nullable=False),
        sa.Column("runner_profile", sa.Text(), nullable=False),
        sa.Column("resource_class", sa.Text(), nullable=False),
        sa.Column(
            "priority_class",
            sa.Text(),
            nullable=False,
            server_default="default",
        ),
        sa.Column("resource_flavor", sa.Text(), nullable=True),
        sa.Column(
            "max_concurrency",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "desired_worker_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "model_profile",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "state",
            sa.Text(),
            nullable=False,
            server_default="available",
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
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
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_host_resource_lanes_workspace_scope
        ON host_resource_lanes (workspace_id, capability_scope)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_host_resource_lanes_capability_kind
        ON host_resource_lanes (capability_scope, kind)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_host_resource_lanes_queue_shard
        ON host_resource_lanes (queue_shard)
        """
    )
    op.execute(
        """
        INSERT INTO host_resource_lanes (
            lane_id,
            workspace_id,
            capability_scope,
            label,
            kind,
            queue_shard,
            runner_profile,
            resource_class,
            priority_class,
            resource_flavor,
            max_concurrency,
            desired_worker_count,
            model_profile,
            state,
            metadata
        ) VALUES (
            'runner:vision_mlx_high',
            NULL,
            'ig',
            'Vision MLX High',
            'vision_analyze',
            'vision_mlx_high',
            'vision_mlx_high',
            'compute',
            'interactive_high',
            'local.mlx.vision',
            1,
            0,
            '{"port":8211}'::jsonb,
            'available',
            '{"seed":"host_resource_lanes_v1"}'::jsonb
        )
        ON CONFLICT (lane_id) DO NOTHING
        """
    )


def downgrade():
    op.drop_index(
        "idx_host_resource_lanes_queue_shard",
        table_name="host_resource_lanes",
    )
    op.drop_index(
        "idx_host_resource_lanes_capability_kind",
        table_name="host_resource_lanes",
    )
    op.drop_index(
        "idx_host_resource_lanes_workspace_scope",
        table_name="host_resource_lanes",
    )
    op.drop_table("host_resource_lanes")
