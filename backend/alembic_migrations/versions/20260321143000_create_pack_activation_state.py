"""Create pack activation state table

Revision ID: 20260321143000
Revises: 20260321083000
Create Date: 2026-03-21 14:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260321143000"
down_revision = "20260321083000"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pack_activation_state",
        sa.Column("pack_id", sa.String(), primary_key=True),
        sa.Column("pack_family", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("install_state", sa.String(), nullable=False),
        sa.Column("migration_state", sa.String(), nullable=False),
        sa.Column("activation_state", sa.String(), nullable=False),
        sa.Column("activation_mode", sa.String(), nullable=False),
        sa.Column("manifest_hash", sa.String(), nullable=True),
        sa.Column("registered_prefixes", sa.JSON(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index(
        "idx_pack_activation_state_enabled",
        "pack_activation_state",
        ["enabled", "activation_state"],
        unique=False,
    )


def downgrade():
    op.drop_index("idx_pack_activation_state_enabled", table_name="pack_activation_state")
    op.drop_table("pack_activation_state")
