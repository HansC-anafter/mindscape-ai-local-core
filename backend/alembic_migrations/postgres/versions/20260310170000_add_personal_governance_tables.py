"""Add personal governance tables

Revision ID: 20260310170000
Create Date: 2026-03-10

ADR-001 v2 Phase 0 — Foundation tables for Personal Governance Runtime.
Creates 5 tables in mindscape_core DB:
  - session_digests: L1→L2 bridge, unified cross-source summaries
  - personal_knowledge: L3 self-model, curated personal mental assets
  - goal_ledger: L3 goal tracking with transaction-log semantics
  - meta_scopes: L4 dynamic governance range selectors
  - writeback_receipts: audit trail for meta meeting writebacks
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "20260310170000"
down_revision = "20260224000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create personal governance tables."""

    # ---------- session_digests ----------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS session_digests (
            id                  TEXT PRIMARY KEY,
            source_type         TEXT NOT NULL DEFAULT '',
            source_id           TEXT NOT NULL DEFAULT '',
            source_time_start   TIMESTAMPTZ,
            source_time_end     TIMESTAMPTZ,
            digest_version      TEXT NOT NULL DEFAULT '1.0',
            owner_profile_id    TEXT NOT NULL,
            workspace_refs      JSONB DEFAULT '[]',
            project_refs        JSONB DEFAULT '[]',
            participants        JSONB DEFAULT '[]',
            summary_md          TEXT NOT NULL DEFAULT '',
            claims              JSONB DEFAULT '[]',
            actions             JSONB DEFAULT '[]',
            decisions           JSONB DEFAULT '[]',
            embedding_text      TEXT NOT NULL DEFAULT '',
            provenance_refs     JSONB DEFAULT '[]',
            sensitivity         TEXT NOT NULL DEFAULT 'private',
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            metadata            JSONB DEFAULT '{}'
        );
    """
    )
    op.create_index("idx_sd_owner", "session_digests", ["owner_profile_id"])
    op.create_index("idx_sd_source", "session_digests", ["source_type", "source_id"])
    op.create_index("idx_sd_created", "session_digests", ["created_at"])

    # ---------- personal_knowledge ----------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS personal_knowledge (
            id                  TEXT PRIMARY KEY,
            owner_profile_id    TEXT NOT NULL,
            knowledge_type      TEXT NOT NULL DEFAULT 'preference',
            content             TEXT NOT NULL DEFAULT '',
            status              TEXT NOT NULL DEFAULT 'candidate',
            confidence          REAL DEFAULT 0.5,
            source_evidence     JSONB DEFAULT '[]',
            source_workspace_ids JSONB DEFAULT '[]',
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_verified_at    TIMESTAMPTZ,
            expires_at          TIMESTAMPTZ,
            valid_scope         TEXT NOT NULL DEFAULT 'global',
            metadata            JSONB DEFAULT '{}'
        );
    """
    )
    op.create_index("idx_pk_owner", "personal_knowledge", ["owner_profile_id"])
    op.create_index("idx_pk_type", "personal_knowledge", ["knowledge_type"])
    op.create_index("idx_pk_status", "personal_knowledge", ["status"])

    # ---------- goal_ledger ----------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS goal_ledger (
            id                  TEXT PRIMARY KEY,
            owner_profile_id    TEXT NOT NULL,
            title               TEXT NOT NULL DEFAULT '',
            description         TEXT NOT NULL DEFAULT '',
            status              TEXT NOT NULL DEFAULT 'candidate',
            horizon             TEXT NOT NULL DEFAULT 'open-ended',
            source_digest_ids   JSONB DEFAULT '[]',
            source_session_ids  JSONB DEFAULT '[]',
            related_knowledge_ids JSONB DEFAULT '[]',
            last_updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            update_count        INTEGER DEFAULT 0,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_mentioned_at   TIMESTAMPTZ,
            confirmed_at        TIMESTAMPTZ,
            metadata            JSONB DEFAULT '{}'
        );
    """
    )
    op.create_index("idx_gl_owner", "goal_ledger", ["owner_profile_id"])
    op.create_index("idx_gl_status", "goal_ledger", ["status"])

    # ---------- meta_scopes ----------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS meta_scopes (
            id                      TEXT PRIMARY KEY,
            owner_profile_id        TEXT NOT NULL,
            scope_kind              TEXT NOT NULL DEFAULT 'manual',
            included_workspaces     JSONB DEFAULT '[]',
            included_projects       JSONB DEFAULT '[]',
            included_inboxes        JSONB DEFAULT '[]',
            time_window             TEXT NOT NULL DEFAULT '7d',
            goal_horizon            TEXT NOT NULL DEFAULT 'open-ended',
            purpose                 TEXT NOT NULL DEFAULT 'review',
            scope_snapshot_at       TIMESTAMPTZ,
            scope_resolution_strategy TEXT NOT NULL DEFAULT 'latest_at_snapshot',
            resolved_digest_ids     JSONB DEFAULT '[]',
            resolved_workspace_states JSONB DEFAULT '{}',
            created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
            metadata                JSONB DEFAULT '{}'
        );
    """
    )
    op.create_index("idx_ms_owner", "meta_scopes", ["owner_profile_id"])

    # ---------- writeback_receipts ----------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS writeback_receipts (
            id                  TEXT PRIMARY KEY,
            meta_session_id     TEXT NOT NULL DEFAULT '',
            source_decision_id  TEXT NOT NULL DEFAULT '',
            target_table        TEXT NOT NULL DEFAULT '',
            target_id           TEXT NOT NULL DEFAULT '',
            writeback_type      TEXT NOT NULL DEFAULT '',
            status              TEXT NOT NULL DEFAULT 'completed',
            error_detail        TEXT,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            metadata            JSONB DEFAULT '{}'
        );
    """
    )
    op.create_index("idx_wr_session", "writeback_receipts", ["meta_session_id"])
    op.create_index(
        "idx_wr_target", "writeback_receipts", ["target_table", "target_id"]
    )


def downgrade() -> None:
    """Drop personal governance tables."""
    for table in [
        "writeback_receipts",
        "meta_scopes",
        "goal_ledger",
        "personal_knowledge",
        "session_digests",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
