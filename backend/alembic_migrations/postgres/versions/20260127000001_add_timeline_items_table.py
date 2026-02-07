"""Add timeline_items table

Revision ID: 20260127000001
Revises: 20260130000009
Create Date: 2026-01-27

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260127000001"
down_revision: Union[str, None] = "9c14677ddefc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create timeline_items table."""
    op.create_table(
        "timeline_items",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(64),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("message_id", sa.String(64), nullable=True),
        sa.Column(
            "task_id",
            sa.String(64),
            sa.ForeignKey("tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("data", sa.Text(), nullable=True),
        sa.Column("cta", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    # Create indexes
    op.create_index(
        "ix_timeline_items_workspace_id", "timeline_items", ["workspace_id"]
    )
    op.create_index("ix_timeline_items_message_id", "timeline_items", ["message_id"])
    op.create_index("ix_timeline_items_task_id", "timeline_items", ["task_id"])
    op.create_index("ix_timeline_items_type", "timeline_items", ["type"])
    op.create_index("ix_timeline_items_created_at", "timeline_items", ["created_at"])
    op.create_index(
        "ix_timeline_items_workspace_created_at",
        "timeline_items",
        ["workspace_id", "created_at"],
    )


def downgrade() -> None:
    """Drop timeline_items table."""
    op.drop_index("ix_timeline_items_workspace_created_at", table_name="timeline_items")
    op.drop_index("ix_timeline_items_created_at", table_name="timeline_items")
    op.drop_index("ix_timeline_items_type", table_name="timeline_items")
    op.drop_index("ix_timeline_items_task_id", table_name="timeline_items")
    op.drop_index("ix_timeline_items_message_id", table_name="timeline_items")
    op.drop_index("ix_timeline_items_workspace_id", table_name="timeline_items")
    op.drop_table("timeline_items")
