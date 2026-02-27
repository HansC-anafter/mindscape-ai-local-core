"""Add auth_status column to runtime_environments

Revision ID: 20260215000001
Revises:
Create Date: 2026-02-15
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "20260215000001"
down_revision = "20260201000000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add auth_status column with default 'disconnected'
    op.add_column(
        "runtime_environments",
        sa.Column(
            "auth_status",
            sa.String(),
            nullable=False,
            server_default="disconnected",
        ),
    )
    op.create_index(
        "ix_runtime_environments_auth_status",
        "runtime_environments",
        ["auth_status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_runtime_environments_auth_status",
        table_name="runtime_environments",
    )
    op.drop_column("runtime_environments", "auth_status")
