"""Add runtime_config_overrides table

Revision ID: 20260216000002
Revises: 20260216000001
Create Date: 2026-02-16 05:40:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260216000002"
down_revision = "20260216000001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "runtime_config_overrides",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("runtime_id", sa.String(), nullable=False),
        sa.Column("scope", sa.String(), nullable=False, server_default="workspace"),
        sa.Column(
            "config_overrides",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
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
        sa.UniqueConstraint(
            "workspace_id", "runtime_id", name="uq_workspace_runtime_override"
        ),
    )
    op.create_index(
        "ix_runtime_config_overrides_workspace_id",
        "runtime_config_overrides",
        ["workspace_id"],
    )
    op.create_index(
        "ix_runtime_config_overrides_runtime_id",
        "runtime_config_overrides",
        ["runtime_id"],
    )


def downgrade():
    op.drop_index(
        "ix_runtime_config_overrides_runtime_id", table_name="runtime_config_overrides"
    )
    op.drop_index(
        "ix_runtime_config_overrides_workspace_id",
        table_name="runtime_config_overrides",
    )
    op.drop_table("runtime_config_overrides")
