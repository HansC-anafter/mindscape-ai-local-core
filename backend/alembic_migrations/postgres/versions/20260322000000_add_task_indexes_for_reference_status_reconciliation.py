"""Add task indexes for IG reference status reconciliation

Revision ID: 20260322000000
Revises: 20260311000000
Create Date: 2026-03-22 03:05:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "20260322000000"
down_revision = "20260311000000"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_tasks_ws_pack_created_at
            ON tasks (workspace_id, pack_id, created_at DESC)
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_tasks_ws_pack_ref_created_at
            ON tasks (
                workspace_id,
                pack_id,
                (COALESCE(execution_context->'inputs'->>'reference_id', '')),
                created_at DESC
            )
            """
        )
    )


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text("DROP INDEX IF EXISTS idx_tasks_ws_pack_ref_created_at"))
    conn.execute(sa.text("DROP INDEX IF EXISTS idx_tasks_ws_pack_created_at"))
