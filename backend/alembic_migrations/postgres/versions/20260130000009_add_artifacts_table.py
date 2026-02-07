"""Add artifacts table

Revision ID: 20260130000009
Revises: 20260130000008
Create Date: 2026-01-27 12:30:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260130000009"
down_revision = "20260130000008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create artifacts table for storing playbook outputs."""
    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(64),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("intent_id", sa.String(64), nullable=True),
        sa.Column("task_id", sa.String(64), nullable=True),
        sa.Column("execution_id", sa.String(64), nullable=True),
        sa.Column("thread_id", sa.String(64), nullable=True),
        sa.Column("playbook_code", sa.Text(), nullable=False),
        sa.Column("artifact_type", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("storage_ref", sa.Text(), nullable=True),
        sa.Column("sync_state", sa.Text(), nullable=True),
        sa.Column(
            "primary_action_type",
            sa.Text(),
            nullable=False,
            server_default="download",
        ),
        sa.Column("metadata", sa.Text(), nullable=True),
        sa.Column("source_execution_id", sa.String(64), nullable=True),
        sa.Column("source_step_id", sa.String(64), nullable=True),
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

    # Create indexes for common queries
    op.create_index("ix_artifacts_workspace_id", "artifacts", ["workspace_id"])
    op.create_index("ix_artifacts_task_id", "artifacts", ["task_id"])
    op.create_index("ix_artifacts_execution_id", "artifacts", ["execution_id"])
    op.create_index("ix_artifacts_thread_id", "artifacts", ["thread_id"])
    op.create_index("ix_artifacts_playbook_code", "artifacts", ["playbook_code"])
    op.create_index("ix_artifacts_created_at", "artifacts", ["created_at"])


def downgrade() -> None:
    """Drop artifacts table."""
    op.drop_index("ix_artifacts_created_at", table_name="artifacts")
    op.drop_index("ix_artifacts_playbook_code", table_name="artifacts")
    op.drop_index("ix_artifacts_thread_id", table_name="artifacts")
    op.drop_index("ix_artifacts_execution_id", table_name="artifacts")
    op.drop_index("ix_artifacts_task_id", table_name="artifacts")
    op.drop_index("ix_artifacts_workspace_id", table_name="artifacts")
    op.drop_table("artifacts")
