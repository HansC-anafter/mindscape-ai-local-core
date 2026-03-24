"""Add canonical memory contract tables

Revision ID: 20260325093000
Revises: 20260310183000
Create Date: 2026-03-25 09:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260325093000"
down_revision = "20260310183000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS memory_items (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                layer TEXT NOT NULL,
                scope TEXT NOT NULL DEFAULT 'global',
                subject_type TEXT NOT NULL DEFAULT '',
                subject_id TEXT NOT NULL DEFAULT '',
                context_type TEXT NOT NULL DEFAULT '',
                context_id TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                claim TEXT NOT NULL DEFAULT '',
                summary TEXT NOT NULL DEFAULT '',
                salience REAL NOT NULL DEFAULT 0.5,
                confidence REAL NOT NULL DEFAULT 0.5,
                verification_status TEXT NOT NULL DEFAULT 'observed',
                lifecycle_status TEXT NOT NULL DEFAULT 'candidate',
                valid_from TIMESTAMPTZ,
                valid_to TIMESTAMPTZ,
                observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                last_confirmed_at TIMESTAMPTZ,
                last_used_at TIMESTAMPTZ,
                update_mode TEXT,
                supersedes_memory_id TEXT,
                created_by_pipeline TEXT NOT NULL DEFAULT '',
                created_from_run_id TEXT,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_memory_items_subject
            ON memory_items (subject_type, subject_id, layer, kind)
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_memory_items_context
            ON memory_items (context_type, context_id, layer)
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_memory_items_lifecycle
            ON memory_items (lifecycle_status, verification_status, observed_at DESC)
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_memory_items_run
            ON memory_items (created_from_run_id)
            """
        )
    )

    conn.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS memory_versions (
                id TEXT PRIMARY KEY,
                memory_item_id TEXT NOT NULL,
                version_no INTEGER NOT NULL,
                update_mode TEXT NOT NULL,
                claim_snapshot TEXT NOT NULL DEFAULT '',
                summary_snapshot TEXT,
                metadata_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                created_from_run_id TEXT
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_memory_versions_item_version
            ON memory_versions (memory_item_id, version_no)
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_memory_versions_run
            ON memory_versions (created_from_run_id)
            """
        )
    )

    conn.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS memory_evidence_links (
                id TEXT PRIMARY KEY,
                memory_item_id TEXT NOT NULL,
                evidence_type TEXT NOT NULL,
                evidence_id TEXT NOT NULL,
                link_role TEXT NOT NULL,
                excerpt TEXT,
                confidence REAL,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_memory_evidence_links_identity
            ON memory_evidence_links (memory_item_id, evidence_type, evidence_id, link_role)
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_memory_evidence_links_memory
            ON memory_evidence_links (memory_item_id, created_at DESC)
            """
        )
    )

    conn.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS memory_edges (
                id TEXT PRIMARY KEY,
                from_memory_id TEXT NOT NULL,
                to_memory_id TEXT NOT NULL,
                edge_type TEXT NOT NULL,
                weight REAL,
                valid_from TIMESTAMPTZ NOT NULL DEFAULT now(),
                valid_to TIMESTAMPTZ,
                evidence_strength REAL,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            ALTER TABLE memory_edges
            DROP CONSTRAINT IF EXISTS chk_memory_edges_edge_type
            """
        )
    )
    conn.execute(
        sa.text(
            """
            ALTER TABLE memory_edges
            ADD CONSTRAINT chk_memory_edges_edge_type
            CHECK (edge_type IN ('supports', 'contradicts', 'derived_from', 'continues', 'supersedes'))
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_memory_edges_from
            ON memory_edges (from_memory_id, edge_type)
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_memory_edges_to
            ON memory_edges (to_memory_id, edge_type)
            """
        )
    )

    conn.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS memory_writeback_runs (
                id TEXT PRIMARY KEY,
                run_type TEXT NOT NULL,
                source_scope TEXT NOT NULL,
                source_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'running',
                idempotency_key TEXT NOT NULL,
                update_mode_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
                started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                completed_at TIMESTAMPTZ,
                summary JSONB NOT NULL DEFAULT '{}'::jsonb,
                error_detail TEXT,
                last_stage TEXT NOT NULL DEFAULT 'created',
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_memory_writeback_runs_idempotency
            ON memory_writeback_runs (idempotency_key)
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_memory_writeback_runs_source
            ON memory_writeback_runs (run_type, source_scope, source_id)
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_memory_writeback_runs_status
            ON memory_writeback_runs (status, started_at DESC)
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    for index_name in [
        "idx_memory_writeback_runs_status",
        "idx_memory_writeback_runs_source",
        "uq_memory_writeback_runs_idempotency",
        "idx_memory_edges_to",
        "idx_memory_edges_from",
        "idx_memory_evidence_links_memory",
        "uq_memory_evidence_links_identity",
        "idx_memory_versions_run",
        "uq_memory_versions_item_version",
        "idx_memory_items_run",
        "idx_memory_items_lifecycle",
        "idx_memory_items_context",
        "idx_memory_items_subject",
    ]:
        conn.execute(sa.text(f"DROP INDEX IF EXISTS {index_name}"))

    conn.execute(
        sa.text(
            "ALTER TABLE memory_edges DROP CONSTRAINT IF EXISTS chk_memory_edges_edge_type"
        )
    )

    for table in [
        "memory_writeback_runs",
        "memory_edges",
        "memory_evidence_links",
        "memory_versions",
        "memory_items",
    ]:
        conn.execute(sa.text(f"DROP TABLE IF EXISTS {table} CASCADE"))
