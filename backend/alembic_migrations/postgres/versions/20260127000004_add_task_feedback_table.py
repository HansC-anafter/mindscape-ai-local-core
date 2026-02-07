"""Add task_feedback table

Revision ID: 20260127000004
Revises: 20260127000003
Create Date: 2026-01-27

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260127000004"
down_revision: Union[str, None] = "20260127000003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create task_feedback table."""
    op.create_table(
        "task_feedback",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "task_id",
            sa.String(64),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            sa.String(64),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    # Create indexes
    op.create_index("ix_task_feedback_task_id", "task_feedback", ["task_id"])
    op.create_index("ix_task_feedback_workspace_id", "task_feedback", ["workspace_id"])
    op.create_index("ix_task_feedback_user_id", "task_feedback", ["user_id"])
    op.create_index("ix_task_feedback_action", "task_feedback", ["action"])
    op.create_index("ix_task_feedback_created_at", "task_feedback", ["created_at"])


def downgrade() -> None:
    """Drop task_feedback table."""
    op.drop_index("ix_task_feedback_created_at", table_name="task_feedback")
    op.drop_index("ix_task_feedback_action", table_name="task_feedback")
    op.drop_index("ix_task_feedback_user_id", table_name="task_feedback")
    op.drop_index("ix_task_feedback_workspace_id", table_name="task_feedback")
    op.drop_index("ix_task_feedback_task_id", table_name="task_feedback")
    op.drop_table("task_feedback")
