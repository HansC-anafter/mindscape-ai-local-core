"""Add project_id scope to meeting_sessions.

Revision ID: 20260222000005
Revises: 20260222000004
Create Date: 2026-02-22 10:35:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260222000005"
down_revision = "20260222000004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "meeting_sessions",
        sa.Column("project_id", sa.Text(), nullable=True),
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_meeting_sessions_ws_project
        ON meeting_sessions(workspace_id, project_id)
        """
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_meeting_sessions_ws_project")
    op.drop_column("meeting_sessions", "project_id")
