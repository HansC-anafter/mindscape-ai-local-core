"""Add active execution projection index.

Revision ID: 20260529124000
Revises: 20260529123000
Create Date: 2026-05-29 12:40:00.000000
"""

from alembic import op


revision = "20260529124000"
down_revision = "20260529123000"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_task_summary_projection_active_status_pack_updated
            ON task_summary_projection (
                workspace_id,
                status,
                pack_id text_pattern_ops,
                updated_at DESC NULLS LAST,
                task_id DESC
            )
            WHERE execution_id IS NOT NULL
              AND status IN ('running', 'queued', 'pending', 'paused')
              AND COALESCE(blocked_reason, '') <> 'admission_deferred'
              AND (
                  frontier_state IS NULL
                  OR frontier_state IN ('ready', 'running')
              )
            """
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS idx_task_summary_projection_active_status_pack_updated"
        )
