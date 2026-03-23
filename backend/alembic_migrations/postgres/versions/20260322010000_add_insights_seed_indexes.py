"""Add indexes for IG insights seeds listing

Revision ID: 20260322010000
Revises: 20260322000000
Create Date: 2026-03-22 05:10:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "20260322010000"
down_revision = "20260322000000"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_ig_accounts_flat_ws_seed_captured_desc
            ON ig_accounts_flat (workspace_id, seed, captured_at DESC)
            INCLUDE (follower_count)
            WHERE seed IS NOT NULL AND seed <> ''
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_ig_accounts_flat_ws_handle_seed_self_enriched
            ON ig_accounts_flat (workspace_id, handle)
            WHERE seed = handle
              AND (
                following_count IS NOT NULL
                OR bio IS NOT NULL
                OR profile_picture_url IS NOT NULL
              )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_ig_account_profiles_ws_seed
            ON ig_account_profiles (workspace_id, seed)
            WHERE seed IS NOT NULL
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_ig_follow_edges_ws_discovered_seed
            ON ig_follow_edges (workspace_id, discovered_via_seed)
            WHERE discovered_via_seed IS NOT NULL
            """
        )
    )


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text("DROP INDEX IF EXISTS idx_ig_follow_edges_ws_discovered_seed"))
    conn.execute(sa.text("DROP INDEX IF EXISTS idx_ig_account_profiles_ws_seed"))
    conn.execute(sa.text("DROP INDEX IF EXISTS idx_ig_accounts_flat_ws_handle_seed_self_enriched"))
    conn.execute(sa.text("DROP INDEX IF EXISTS idx_ig_accounts_flat_ws_seed_captured_desc"))
