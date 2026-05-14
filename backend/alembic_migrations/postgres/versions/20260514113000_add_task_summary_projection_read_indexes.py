"""Add task summary projection read indexes.

Revision ID: 20260514113000
Revises: 20260514103000
Create Date: 2026-05-14 11:30:00.000000
"""

from alembic import op


revision = "20260514113000"
down_revision = "20260514103000"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_task_summary_projection_exec_created
            ON task_summary_projection (
                workspace_id,
                created_at DESC NULLS LAST,
                task_id DESC
            )
            WHERE execution_id IS NOT NULL
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_task_summary_projection_include_order
            ON task_summary_projection (
                workspace_id,
                (CASE WHEN status = 'running' THEN 0 ELSE 1 END),
                created_at DESC NULLS LAST,
                updated_at DESC,
                task_id DESC
            )
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_task_summary_projection_ready_order
            ON task_summary_projection (
                workspace_id,
                (CASE
                    WHEN status = 'pending' THEN 0
                    WHEN status = 'running' THEN 1
                    ELSE 2
                END),
                created_at DESC NULLS LAST,
                updated_at DESC,
                task_id DESC
            )
            WHERE status IN ('pending', 'running')
            """
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS idx_task_summary_projection_ready_order"
        )
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS idx_task_summary_projection_include_order"
        )
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS idx_task_summary_projection_exec_created"
        )
