"""Add durable capability install jobs.

Revision ID: 20260529110000
Revises: 20260522143000
Create Date: 2026-05-29 11:00:00.000000
"""

from alembic import op


revision = "20260529110000"
down_revision = "20260522143000"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS capability_install_jobs (
            install_id            TEXT PRIMARY KEY,
            source_kind           TEXT NOT NULL,
            state                 TEXT NOT NULL DEFAULT 'queued',
            source_payload        JSONB NOT NULL DEFAULT '{}'::jsonb,
            result_payload        JSONB NOT NULL DEFAULT '{}'::jsonb,
            error                 TEXT,
            retry_after_seconds   INTEGER,
            not_before            TIMESTAMPTZ,
            created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
            started_at            TIMESTAMPTZ,
            finished_at           TIMESTAMPTZ
        )
        """
    )
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_capability_install_jobs_state "
            "ON capability_install_jobs(state)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_capability_install_jobs_not_before "
            "ON capability_install_jobs(not_before)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_capability_install_jobs_created_at "
            "ON capability_install_jobs(created_at)"
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS idx_capability_install_jobs_created_at"
        )
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS idx_capability_install_jobs_not_before"
        )
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_capability_install_jobs_state")
    op.execute("DROP TABLE IF EXISTS capability_install_jobs")
