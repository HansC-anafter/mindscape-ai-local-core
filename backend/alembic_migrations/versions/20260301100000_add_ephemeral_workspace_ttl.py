"""Add ephemeral workspace TTL columns

Revision ID: 20260301100000
Revises: 20260301000000
Create Date: 2026-03-01 10:00:00.000000

PF-2: Persist ttl_hours, expires_at, parent_workspace_id for
ephemeral workspace lifecycle management.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260301100000"
down_revision: Union[str, None] = "20260301000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workspaces",
        sa.Column("ttl_hours", sa.Integer(), nullable=True),
    )
    op.add_column(
        "workspaces",
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "workspaces",
        sa.Column("parent_workspace_id", sa.String(64), nullable=True),
    )
    op.add_column(
        "workspaces",
        sa.Column(
            "visibility",
            sa.String(16),
            server_default="private",
            nullable=False,
        ),
    )
    op.create_index(
        "idx_ws_expires_at",
        "workspaces",
        ["expires_at"],
        postgresql_where=sa.text("expires_at IS NOT NULL"),
    )
    op.create_index(
        "idx_ws_parent",
        "workspaces",
        ["parent_workspace_id"],
        postgresql_where=sa.text("parent_workspace_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_ws_parent", table_name="workspaces")
    op.drop_index("idx_ws_expires_at", table_name="workspaces")
    op.drop_column("workspaces", "visibility")
    op.drop_column("workspaces", "parent_workspace_id")
    op.drop_column("workspaces", "expires_at")
    op.drop_column("workspaces", "ttl_hours")
