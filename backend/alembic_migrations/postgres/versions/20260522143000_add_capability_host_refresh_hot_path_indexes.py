"""Add capability host refresh hot path indexes.

Revision ID: 20260522143000
Revises: 20260521173000
Create Date: 2026-05-22 14:30:00.000000
"""

from alembic import op


revision = "20260522143000"
down_revision = "20260521173000"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_workspace_run_feed_workspace_source_run_latest
            ON workspace_run_feed (
                workspace_id,
                source_kind,
                run_id,
                occurred_at DESC,
                feed_id DESC
            )
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_runs_workspace_source_status_updated_run
            ON runs (
                workspace_id,
                source_kind,
                status,
                updated_at DESC,
                run_id DESC
            )
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_task_summary_projection_workspace_status_pack_updated
            ON task_summary_projection (
                workspace_id,
                status,
                pack_id text_pattern_ops,
                updated_at DESC,
                task_id DESC
            )
            WHERE execution_id IS NOT NULL
              AND COALESCE(blocked_reason, '') <> 'admission_deferred'
            """
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS idx_task_summary_projection_workspace_status_pack_updated"
        )
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS idx_runs_workspace_source_status_updated_run"
        )
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS idx_workspace_run_feed_workspace_source_run_latest"
        )
