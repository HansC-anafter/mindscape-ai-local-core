"""Baseline: create reasoning_traces table if not exists.

Revision ID: 20260222000000
Revises: 20260216000002
Create Date: 2026-02-22 00:00:00.000000

This is an idempotent baseline migration that ensures the reasoning_traces
table exists. The table may have been created by runtime DDL in
reasoning_traces_store.py. Using CREATE TABLE IF NOT EXISTS ensures
compatibility with both fresh installs and existing deployments.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "20260222000000"
down_revision = "20260216000002"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS reasoning_traces (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            execution_id TEXT,
            assistant_event_id TEXT,
            graph_json JSONB NOT NULL,
            schema_version INTEGER NOT NULL DEFAULT 1,
            sgr_mode VARCHAR(20) NOT NULL DEFAULT 'inline',
            model VARCHAR(100),
            token_count INTEGER,
            latency_ms INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """
    )
    # Idempotent indexes (safe if runtime DDL already created them)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_reasoning_traces_workspace "
        "ON reasoning_traces(workspace_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_reasoning_traces_exec "
        "ON reasoning_traces(execution_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_reasoning_traces_event "
        "ON reasoning_traces(assistant_event_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_reasoning_traces_created "
        "ON reasoning_traces(created_at DESC)"
    )


def downgrade():
    # No-op: do not drop table to prevent data loss.
    # Runtime DDL may have already created this table with data.
    pass
