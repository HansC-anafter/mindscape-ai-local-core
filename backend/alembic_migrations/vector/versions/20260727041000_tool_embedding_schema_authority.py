"""Move the Tool RAG vector schema behind migration authority.

Revision ID: 20260727041000
Revises: 20260727040000
Create Date: 2026-07-27
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text


revision = "20260727041000"
down_revision = "20260727040000"
branch_labels = None
depends_on = None

RUNTIME_ROLE = "mindscape_vector_runtime"
REQUIRED_COLUMNS = {
    "id",
    "tool_id",
    "display_name",
    "description",
    "category",
    "capability_code",
    "embedding",
    "embedding_model",
    "embedding_dim",
    "affordance",
    "created_at",
    "updated_at",
    "text_vector",
}


def _create_or_adopt_table() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.tool_embeddings (
            id SERIAL PRIMARY KEY,
            tool_id TEXT NOT NULL,
            display_name TEXT,
            description TEXT NOT NULL,
            category TEXT,
            capability_code TEXT,
            embedding vector,
            embedding_model TEXT NOT NULL,
            embedding_dim INTEGER NOT NULL,
            affordance JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (tool_id, embedding_model)
        )
        """
    )
    op.execute(
        """
        ALTER TABLE public.tool_embeddings
        ADD COLUMN IF NOT EXISTS affordance JSONB DEFAULT '{}'::jsonb
        """
    )
    op.execute(
        """
        ALTER TABLE public.tool_embeddings
        ADD COLUMN IF NOT EXISTS text_vector TSVECTOR
        GENERATED ALWAYS AS (
            to_tsvector(
                'simple',
                COALESCE(display_name, '') || ' ' || description
            )
        ) STORED
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_tool_embeddings_text
        ON public.tool_embeddings USING gin (text_vector)
        """
    )


def _verify_shape() -> None:
    rows = op.get_bind().execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'tool_embeddings'
            """
        )
    )
    observed = {str(row[0]) for row in rows}
    missing = sorted(REQUIRED_COLUMNS - observed)
    if missing:
        raise RuntimeError(
            "tool_embeddings_migration_shape_mismatch:"
            + ",".join(missing)
        )
    index_exists = bool(
        op.get_bind()
        .execute(
            text(
                """
                SELECT to_regclass(
                    'public.idx_tool_embeddings_text'
                ) IS NOT NULL
                """
            )
        )
        .scalar()
    )
    if not index_exists:
        raise RuntimeError("tool_embeddings_text_index_missing")


def _grant_runtime_dml() -> None:
    op.execute(
        f"""
        GRANT SELECT, INSERT, UPDATE, DELETE
        ON TABLE public.tool_embeddings TO {RUNTIME_ROLE}
        """
    )
    op.execute(
        f"""
        GRANT USAGE, SELECT
        ON SEQUENCE public.tool_embeddings_id_seq TO {RUNTIME_ROLE}
        """
    )


def upgrade() -> None:
    _create_or_adopt_table()
    _verify_shape()
    _grant_runtime_dml()


def downgrade() -> None:
    # The revision may adopt a pre-existing runtime table and must not drop it.
    pass
