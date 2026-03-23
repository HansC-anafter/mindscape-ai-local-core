"""Add indexes for IG insights targets listing

Revision ID: 20260322020000
Revises: 20260322010000
Create Date: 2026-03-22 06:20:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "20260322020000"
down_revision = "20260322010000"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_ig_accounts_flat_targets_ws_handle_captured_desc
            ON ig_accounts_flat (workspace_id, handle, captured_at DESC)
            WHERE COALESCE(NULLIF(source_context, ''), 'following_list') = 'following_list'
              AND handle NOT LIKE '__seed_placeholder__%'
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_ig_accounts_flat_targets_ws_handle_bio_updated_desc
            ON ig_accounts_flat (workspace_id, handle, updated_at DESC)
            WHERE bio IS NOT NULL AND bio <> ''
            """
        )
    )


def downgrade():
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "DROP INDEX IF EXISTS idx_ig_accounts_flat_targets_ws_handle_bio_updated_desc"
        )
    )
    conn.execute(
        sa.text(
            "DROP INDEX IF EXISTS idx_ig_accounts_flat_targets_ws_handle_captured_desc"
        )
    )
