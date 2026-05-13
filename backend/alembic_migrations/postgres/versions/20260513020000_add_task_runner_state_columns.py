"""Add task runner state columns.

Revision ID: 20260513020000
Revises: 20260513010000
Create Date: 2026-05-13 02:00:00.000000
"""

from alembic import op


revision = "20260513020000"
down_revision = "20260513010000"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS runner_id TEXT")
    op.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMPTZ")
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tasks_running_heartbeat_at
            ON tasks (heartbeat_at, started_at, id)
            WHERE status = 'running'
            """
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_tasks_running_heartbeat_at")
    op.execute("ALTER TABLE tasks DROP COLUMN IF EXISTS heartbeat_at")
    op.execute("ALTER TABLE tasks DROP COLUMN IF EXISTS runner_id")
