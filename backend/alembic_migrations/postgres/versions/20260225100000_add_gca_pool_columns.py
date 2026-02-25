"""add gca pool columns to runtime_environments

Revision ID: 20260225100000
Revises: 20260225000000
Create Date: 2026-02-25 10:00:00.000000

Add multi-account pool support columns for GCA account rotation.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260225100000"
down_revision = "20260225000000"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "runtime_environments",
        sa.Column("pool_group", sa.String(), nullable=True),
    )
    op.add_column(
        "runtime_environments",
        sa.Column("pool_enabled", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column(
        "runtime_environments",
        sa.Column("pool_priority", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "runtime_environments",
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "runtime_environments",
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "runtime_environments",
        sa.Column("last_error_code", sa.String(), nullable=True),
    )

    op.create_index("ix_re_pool_group", "runtime_environments", ["pool_group"])
    op.create_index(
        "ix_re_user_pool", "runtime_environments", ["user_id", "pool_group"]
    )

    # Migrate existing gca-local runtime into the pool
    op.execute(
        "UPDATE runtime_environments "
        "SET pool_group = 'gca-pool' "
        "WHERE id = 'gca-local'"
    )


def downgrade():
    op.drop_index("ix_re_user_pool", table_name="runtime_environments")
    op.drop_index("ix_re_pool_group", table_name="runtime_environments")
    op.drop_column("runtime_environments", "last_error_code")
    op.drop_column("runtime_environments", "last_used_at")
    op.drop_column("runtime_environments", "cooldown_until")
    op.drop_column("runtime_environments", "pool_priority")
    op.drop_column("runtime_environments", "pool_enabled")
    op.drop_column("runtime_environments", "pool_group")
