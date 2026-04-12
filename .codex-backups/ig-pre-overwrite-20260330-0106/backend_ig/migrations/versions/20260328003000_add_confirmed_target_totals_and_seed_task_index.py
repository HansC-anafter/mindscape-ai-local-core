"""Add confirmed target totals table and following seed task index

Revision ID: 20260328003000
Revises: 20260323010000
Create Date: 2026-03-28 00:30:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "20260328003000"
down_revision = "20260323010000"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS ig_confirmed_targets (
                workspace_id VARCHAR(255) NOT NULL,
                handle VARCHAR(255) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (workspace_id, handle)
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO ig_confirmed_targets (workspace_id, handle, updated_at)
            SELECT
                workspace_id,
                LOWER(LTRIM(handle, '@')) AS handle,
                MAX(COALESCE(updated_at, CURRENT_TIMESTAMP)) AS updated_at
            FROM ig_accounts_flat
            WHERE COALESCE(NULLIF(source_context, ''), 'following_list') = 'following_list'
              AND handle NOT LIKE '__seed_placeholder__%'
            GROUP BY workspace_id, LOWER(LTRIM(handle, '@'))
            ON CONFLICT (workspace_id, handle) DO UPDATE SET
                updated_at = GREATEST(
                    ig_confirmed_targets.updated_at,
                    EXCLUDED.updated_at
                )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_tasks_ws_pack_seed_key_created_desc
            ON tasks (
                workspace_id,
                pack_id,
                (
                    lower(
                        ltrim(
                            coalesce(
                                execution_context->'inputs'->>'target_username',
                                execution_context->'inputs'->>'target_handle',
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
                started_at,
                completed_at,
                error,
                blocked_reason
            )
            WHERE pack_id = 'ig_analyze_following'
            """
        )
    )


def downgrade():
    conn = op.get_bind()
    conn.execute(
        sa.text("DROP INDEX IF EXISTS idx_tasks_ws_pack_seed_key_created_desc")
    )
    conn.execute(sa.text("DROP TABLE IF EXISTS ig_confirmed_targets"))
