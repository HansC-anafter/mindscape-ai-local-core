"""Add indexes for workspace execution feed reads.

Revision ID: 20260509164000
Revises: 20260507063000
Create Date: 2026-05-09 16:40:00.000000
"""

from alembic import op


revision = "20260509164000"
down_revision = "20260507063000"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_tasks_workspace_status_created_desc
        ON tasks (workspace_id, status, created_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_tasks_workspace_execution_created_desc
        ON tasks (workspace_id, created_at DESC, id DESC)
        WHERE execution_context IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_artifacts_ws_execution_updated_desc
        ON artifacts (workspace_id, execution_id, updated_at DESC, id DESC)
        WHERE content IS NOT NULL
        """
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_artifacts_ws_execution_updated_desc")
    op.execute("DROP INDEX IF EXISTS idx_tasks_workspace_execution_created_desc")
    op.execute("DROP INDEX IF EXISTS idx_tasks_workspace_status_created_desc")
