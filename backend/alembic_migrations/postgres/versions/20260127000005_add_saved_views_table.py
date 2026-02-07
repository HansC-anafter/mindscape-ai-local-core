"""Add saved_views table

Revision ID: 20260127000005
Revises: 20260127000004
Create Date: 2026-01-27

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260127000005"
down_revision: Union[str, None] = "20260127000004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create saved_views table."""
    op.create_table(
        "saved_views",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("scope", sa.String(64), nullable=False, server_default="global"),
        sa.Column("view", sa.String(64), nullable=False, server_default="my_work"),
        sa.Column("tab", sa.String(64), nullable=False, server_default="inbox"),
        sa.Column("filters", sa.Text(), nullable=True, server_default="{}"),
        sa.Column("sort_by", sa.String(64), nullable=True, server_default="auto"),
        sa.Column("sort_order", sa.String(16), nullable=True, server_default="desc"),
        sa.Column("is_default", sa.Boolean(), nullable=True, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    # Create indexes
    op.create_index("ix_saved_views_user_id", "saved_views", ["user_id"])
    op.create_index("ix_saved_views_user_tab", "saved_views", ["user_id", "tab"])


def downgrade() -> None:
    """Drop saved_views table."""
    op.drop_index("ix_saved_views_user_tab", table_name="saved_views")
    op.drop_index("ix_saved_views_user_id", table_name="saved_views")
    op.drop_table("saved_views")
