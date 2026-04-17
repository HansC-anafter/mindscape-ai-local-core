"""Add channel_bindings table

Revision ID: 20260105000000
Revises: 20260103000000
Create Date: 2026-01-05 00:00:00.000000
Capability: mindscape_cloud_integration

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260105000000"
down_revision = "20260103000000"
branch_labels = None
depends_on = None


def _table_exists(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _index_exists(
    inspector: sa.Inspector,
    table_name: str,
    index_name: str,
) -> bool:
    try:
        indexes = inspector.get_indexes(table_name)
    except Exception:
        return False
    return any(index.get("name") == index_name for index in indexes)


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if not _table_exists(inspector, "channel_bindings"):
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
        inspector = sa.inspect(op.get_bind())

    # Create indexes
    index_specs = [
        ("idx_workspace_runtime_channel", ["workspace_id", "runtime_id", "channel_id"]),
        (op.f("ix_channel_bindings_workspace_id"), ["workspace_id"]),
        (op.f("ix_channel_bindings_runtime_id"), ["runtime_id"]),
        (op.f("ix_channel_bindings_channel_id"), ["channel_id"]),
        (op.f("ix_channel_bindings_agency"), ["agency"]),
        (op.f("ix_channel_bindings_tenant"), ["tenant"]),
        (op.f("ix_channel_bindings_chainagent"), ["chainagent"]),
    ]
    for index_name, columns in index_specs:
        if not _index_exists(inspector, "channel_bindings", index_name):
            op.create_index(index_name, "channel_bindings", columns, unique=False)


def downgrade():
    inspector = sa.inspect(op.get_bind())
    if not _table_exists(inspector, "channel_bindings"):
        return

    for index_name in [
        op.f("ix_channel_bindings_chainagent"),
        op.f("ix_channel_bindings_tenant"),
        op.f("ix_channel_bindings_agency"),
        op.f("ix_channel_bindings_channel_id"),
        op.f("ix_channel_bindings_runtime_id"),
        op.f("ix_channel_bindings_workspace_id"),
        "idx_workspace_runtime_channel",
    ]:
        if _index_exists(inspector, "channel_bindings", index_name):
            op.drop_index(index_name, table_name="channel_bindings")
            inspector = sa.inspect(op.get_bind())
    op.drop_table("channel_bindings")
