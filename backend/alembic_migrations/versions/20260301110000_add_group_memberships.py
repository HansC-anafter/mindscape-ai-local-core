"""Add workspace_group_memberships join table

Revision ID: 20260301110000
Revises: 20260301100000
Create Date: 2026-03-01 11:00:00.000000

5D-2: Allows a workspace to belong to multiple groups simultaneously.
Replaces the single-FK workspaces.group_id with a many-to-many relationship.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260301110000"
down_revision: Union[str, None] = "20260301100000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workspace_group_memberships",
        sa.Column("workspace_id", sa.String(64), nullable=False),
        sa.Column("group_id", sa.String(64), nullable=False),
        sa.Column(
            "role",
            sa.String(16),
            server_default="cell",
            nullable=False,
        ),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("workspace_id", "group_id"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["group_id"], ["workspace_groups.id"]),
    )
    op.create_index(
        "idx_wgm_group",
        "workspace_group_memberships",
        ["group_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_wgm_group", table_name="workspace_group_memberships")
    op.drop_table("workspace_group_memberships")
