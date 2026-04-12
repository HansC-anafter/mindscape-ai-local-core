"""Create ig_pin_failed_attempts table

Revision ID: 20260323010000
Revises: 20260322020000
Create Date: 2026-03-23 01:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "20260323010000"
down_revision = "20260322020000"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS ig_pin_failed_attempts (
                id VARCHAR(36) PRIMARY KEY,
                dedupe_key VARCHAR(64) NOT NULL UNIQUE,
                workspace_id VARCHAR(255) NOT NULL,
                source_handle VARCHAR(255),
                source_shortcode VARCHAR(255),
                source_url TEXT,
                image_url TEXT,
                parent_execution_id VARCHAR(36),
                trigger VARCHAR(100),
                base64_image_present BOOLEAN NOT NULL DEFAULT FALSE,
                error_kind VARCHAR(100) NOT NULL,
                error_message TEXT NOT NULL,
                failure_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                status VARCHAR(32) NOT NULL DEFAULT 'pending_retry',
                failure_count INTEGER NOT NULL DEFAULT 1,
                first_failed_at TIMESTAMPTZ NOT NULL,
                last_failed_at TIMESTAMPTZ NOT NULL,
                recovered_at TIMESTAMPTZ,
                recovered_reference_id VARCHAR(255),
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_ig_pin_failed_attempts_ws_status_last_failed
            ON ig_pin_failed_attempts (workspace_id, status, last_failed_at DESC)
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_ig_pin_failed_attempts_parent_execution
            ON ig_pin_failed_attempts (parent_execution_id)
            WHERE parent_execution_id IS NOT NULL
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_ig_pin_failed_attempts_source_handle_last_failed
            ON ig_pin_failed_attempts (workspace_id, source_handle, last_failed_at DESC)
            """
        )
    )


def downgrade():
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "DROP INDEX IF EXISTS idx_ig_pin_failed_attempts_source_handle_last_failed"
        )
    )
    conn.execute(
        sa.text(
            "DROP INDEX IF EXISTS idx_ig_pin_failed_attempts_parent_execution"
        )
    )
    conn.execute(
        sa.text(
            "DROP INDEX IF EXISTS idx_ig_pin_failed_attempts_ws_status_last_failed"
        )
    )
    conn.execute(sa.text("DROP TABLE IF EXISTS ig_pin_failed_attempts"))
