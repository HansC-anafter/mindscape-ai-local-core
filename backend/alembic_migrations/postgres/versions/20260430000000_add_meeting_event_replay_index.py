"""Add fast meeting event replay index

Revision ID: 20260430000000
Revises: 20260428173000
Create Date: 2026-04-30 00:00:00.000000
"""

from alembic import op


revision = "20260430000000"
down_revision = "20260428173000"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mind_events_ws_thread_time_id
        ON mind_events (workspace_id, thread_id, timestamp ASC, id ASC)
        """
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_mind_events_ws_thread_time_id")
