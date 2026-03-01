"""Add workspace_groups table and group columns to workspaces

Revision ID: 20260301000000
Revises: 20260211000000
Create Date: 2026-03-01 00:00:00.000000

Phase 0: Asset-boundary workspace dispatch foundation.
- workspace_groups: new table for grouping workspaces
- workspaces.group_id: FK to workspace_groups
- workspaces.workspace_role: dispatch | cell
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260301000000"
down_revision: Union[str, None] = "20260211000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- workspace_groups table ---
    op.create_table(
        "workspace_groups",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("owner_user_id", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "role_map",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_wg_owner", "workspace_groups", ["owner_user_id"])

    # --- Add group columns to workspaces ---
    op.add_column(
        "workspaces",
        sa.Column("group_id", sa.String(64), nullable=True),
    )
    op.add_column(
        "workspaces",
        sa.Column(
            "workspace_role",
            sa.String(16),
            server_default="cell",
            nullable=True,
        ),
    )
    op.create_index("idx_ws_group", "workspaces", ["group_id"])


def downgrade() -> None:
    op.drop_index("idx_ws_group", table_name="workspaces")
    op.drop_column("workspaces", "workspace_role")
    op.drop_column("workspaces", "group_id")
    op.drop_index("idx_wg_owner", table_name="workspace_groups")
    op.drop_table("workspace_groups")
