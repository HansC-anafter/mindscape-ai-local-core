"""Add channel_bindings table

Revision ID: 20260105000000
Revises: 20260103000000
Create Date: 2026-01-05 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260105000000"
down_revision = "20260103000000"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "channel_bindings" in existing_tables:
        return

    op.create_table(
        "channel_bindings",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("runtime_id", sa.String(), nullable=False),
        sa.Column("channel_id", sa.String(), nullable=False),
        sa.Column("channel_type", sa.String(), nullable=False),
        sa.Column("channel_name", sa.String(), nullable=True),
        sa.Column("agency", sa.String(), nullable=True),
        sa.Column("tenant", sa.String(), nullable=True),
        sa.Column("chainagent", sa.String(), nullable=True),
        sa.Column(
            "binding_config", postgresql.JSON(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column(
            "extra_metadata", postgresql.JSON(astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes
    op.create_index(
        "idx_workspace_runtime_channel",
        "channel_bindings",
        ["workspace_id", "runtime_id", "channel_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_channel_bindings_workspace_id"),
        "channel_bindings",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_channel_bindings_runtime_id"),
        "channel_bindings",
        ["runtime_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_channel_bindings_channel_id"),
        "channel_bindings",
        ["channel_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_channel_bindings_agency"), "channel_bindings", ["agency"], unique=False
    )
    op.create_index(
        op.f("ix_channel_bindings_tenant"), "channel_bindings", ["tenant"], unique=False
    )
    op.create_index(
        op.f("ix_channel_bindings_chainagent"),
        "channel_bindings",
        ["chainagent"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_channel_bindings_chainagent"), table_name="channel_bindings")
    op.drop_index(op.f("ix_channel_bindings_tenant"), table_name="channel_bindings")
    op.drop_index(op.f("ix_channel_bindings_agency"), table_name="channel_bindings")
    op.drop_index(op.f("ix_channel_bindings_channel_id"), table_name="channel_bindings")
    op.drop_index(op.f("ix_channel_bindings_runtime_id"), table_name="channel_bindings")
    op.drop_index(
        op.f("ix_channel_bindings_workspace_id"), table_name="channel_bindings"
    )
    op.drop_index("idx_workspace_runtime_channel", table_name="channel_bindings")
    op.drop_table("channel_bindings")
