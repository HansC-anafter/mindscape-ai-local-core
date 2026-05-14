"""Add task summary projection execution route indexes.

Revision ID: 20260514120000
Revises: 20260514114500
Create Date: 2026-05-14 12:00:00.000000
"""

from alembic import op


revision = "20260514120000"
down_revision = "20260514114500"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_task_summary_projection_parent_created
            ON task_summary_projection (
                workspace_id,
                parent_execution_id,
                created_at DESC NULLS LAST,
                task_id DESC
            )
            WHERE execution_id IS NOT NULL
              AND parent_execution_id IS NOT NULL
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_task_summary_projection_pack_created
            ON task_summary_projection (
                workspace_id,
                pack_id,
                created_at DESC NULLS LAST,
                task_id DESC
            )
            WHERE execution_id IS NOT NULL
              AND pack_id IS NOT NULL
            """
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS idx_task_summary_projection_pack_created"
        )
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS idx_task_summary_projection_parent_created"
        )
