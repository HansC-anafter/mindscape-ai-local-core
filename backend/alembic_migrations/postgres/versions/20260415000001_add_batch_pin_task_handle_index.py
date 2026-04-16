"""Add batch pin task handle index

Revision ID: 20260415000001
Revises: 20260415000000
Create Date: 2026-04-15 12:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260415000001"
down_revision = "20260415000000"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_tasks_ws_pack_batch_pin_handle_created_desc
            ON tasks (
                workspace_id,
                pack_id,
                (
                    lower(
                        ltrim(
                            coalesce(
                                execution_context->'inputs'->>'target_handle',
                                execution_context->'inputs'->>'target_username',
                                execution_context->>'target_handle',
                                execution_context->>'target_username',
                                ''
                            ),
                            '@'
                        )
                    )
                ),
                created_at DESC,
                id DESC
            )
            INCLUDE (
                execution_id,
                status,
                completed_at
            )
            WHERE pack_id = 'ig_batch_pin_references'
            """
        )
    )


def downgrade():
    conn = op.get_bind()
    conn.execute(
        sa.text("DROP INDEX IF EXISTS idx_tasks_ws_pack_batch_pin_handle_created_desc")
    )
