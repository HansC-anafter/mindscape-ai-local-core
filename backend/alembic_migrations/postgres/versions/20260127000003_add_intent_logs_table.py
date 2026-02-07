"""Add intent_logs table

Revision ID: 20260127000003
Revises: 20260127000002
Create Date: 2026-01-27

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260127000003"
down_revision: Union[str, None] = "20260127000002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create intent_logs table."""
    op.create_table(
        "intent_logs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "timestamp",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("raw_input", sa.Text(), nullable=True),
        sa.Column("channel", sa.String(64), nullable=True),
        sa.Column(
            "profile_id",
            sa.String(64),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("project_id", sa.String(64), nullable=True),
        sa.Column(
            "workspace_id",
            sa.String(64),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("pipeline_steps", sa.Text(), nullable=True),
        sa.Column("final_decision", sa.Text(), nullable=True),
        sa.Column("user_override", sa.Text(), nullable=True),
        sa.Column("metadata", sa.Text(), nullable=True),
    )

    # Create indexes
    op.create_index("ix_intent_logs_profile_id", "intent_logs", ["profile_id"])
    op.create_index("ix_intent_logs_workspace_id", "intent_logs", ["workspace_id"])
    op.create_index("ix_intent_logs_timestamp", "intent_logs", ["timestamp"])
    op.create_index(
        "ix_intent_logs_profile_timestamp", "intent_logs", ["profile_id", "timestamp"]
    )
    op.create_index(
        "ix_intent_logs_workspace_timestamp",
        "intent_logs",
        ["workspace_id", "timestamp"],
    )


def downgrade() -> None:
    """Drop intent_logs table."""
    op.drop_index("ix_intent_logs_workspace_timestamp", table_name="intent_logs")
    op.drop_index("ix_intent_logs_profile_timestamp", table_name="intent_logs")
    op.drop_index("ix_intent_logs_timestamp", table_name="intent_logs")
    op.drop_index("ix_intent_logs_workspace_id", table_name="intent_logs")
    op.drop_index("ix_intent_logs_profile_id", table_name="intent_logs")
    op.drop_table("intent_logs")
