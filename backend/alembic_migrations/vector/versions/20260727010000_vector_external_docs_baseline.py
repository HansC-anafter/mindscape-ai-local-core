"""Adopt or create the frozen legacy external_docs vector baseline.

Revision ID: 20260727010000
Revises:
Create Date: 2026-07-27
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text


revision = "20260727010000"
down_revision = None
branch_labels = ("mindscape_vectors",)
depends_on = None


_EXPECTED_COLUMNS = (
    ("id", "uuid", False),
    ("user_id", "text", False),
    ("source_app", "text", False),
    ("source_id", "text", False),
    ("doc_type", "text", True),
    ("title", "text", True),
    ("content", "text", False),
    ("embedding", "vector(1536)", True),
    ("metadata", "jsonb", True),
    ("created_at", "timestamp without time zone", False),
    ("updated_at", "timestamp without time zone", False),
    ("last_synced_at", "timestamp without time zone", True),
)

_EXPECTED_INDEXES = {
    "external_docs_pkey": (True, "btree", ("id",)),
    "idx_external_docs_metadata": (False, "gin", ("metadata",)),
    "idx_external_docs_source": (False, "btree", ("source_app",)),
    "idx_external_docs_source_id": (
        False,
        "btree",
        ("source_app", "source_id"),
    ),
    "idx_external_docs_unique_source": (
        True,
        "btree",
        ("user_id", "source_app", "source_id"),
    ),
    "idx_external_docs_user": (False, "btree", ("user_id",)),
}


def _table_exists() -> bool:
    return bool(
        op.get_bind()
        .execute(text("SELECT to_regclass('public.external_docs') IS NOT NULL"))
        .scalar()
    )


def _create_frozen_table() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE external_docs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id TEXT NOT NULL DEFAULT 'default_user',
            source_app TEXT NOT NULL,
            source_id TEXT NOT NULL,
            doc_type TEXT,
            title TEXT,
            content TEXT NOT NULL,
            embedding vector(1536),
            metadata JSONB,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            last_synced_at TIMESTAMP WITHOUT TIME ZONE
        )
        """
    )
    op.execute("CREATE INDEX idx_external_docs_user ON external_docs (user_id)")
    op.execute("CREATE INDEX idx_external_docs_source ON external_docs (source_app)")
    op.execute(
        "CREATE INDEX idx_external_docs_source_id "
        "ON external_docs (source_app, source_id)"
    )
    op.execute(
        "CREATE INDEX idx_external_docs_metadata "
        "ON external_docs USING gin (metadata)"
    )
    op.execute(
        "CREATE UNIQUE INDEX idx_external_docs_unique_source "
        "ON external_docs (user_id, source_app, source_id)"
    )


def _read_columns() -> tuple[tuple[str, str, bool], ...]:
    rows = op.get_bind().execute(
        text(
            """
            SELECT
                attribute.attname,
                pg_catalog.format_type(attribute.atttypid, attribute.atttypmod),
                NOT attribute.attnotnull
            FROM pg_catalog.pg_attribute AS attribute
            WHERE attribute.attrelid = 'public.external_docs'::regclass
              AND attribute.attnum > 0
              AND NOT attribute.attisdropped
            ORDER BY attribute.attnum
            """
        )
    )
    return tuple((str(row[0]), str(row[1]), bool(row[2])) for row in rows)


def _read_indexes() -> dict[str, tuple[bool, str, tuple[str, ...]]]:
    rows = op.get_bind().execute(
        text(
            """
            SELECT
                index_class.relname,
                index.indisunique,
                access_method.amname,
                ARRAY(
                    SELECT pg_get_indexdef(index.indexrelid, key_position, TRUE)
                    FROM generate_series(1, index.indnkeyatts) AS key_position
                    ORDER BY key_position
                )
            FROM pg_index AS index
            JOIN pg_class AS table_class
              ON table_class.oid = index.indrelid
            JOIN pg_namespace AS namespace
              ON namespace.oid = table_class.relnamespace
            JOIN pg_class AS index_class
              ON index_class.oid = index.indexrelid
            JOIN pg_am AS access_method
              ON access_method.oid = index_class.relam
            WHERE namespace.nspname = 'public'
              AND table_class.relname = 'external_docs'
            ORDER BY index_class.relname
            """
        )
    )
    return {
        str(row[0]): (
            bool(row[1]),
            str(row[2]),
            tuple(str(value) for value in row[3]),
        )
        for row in rows
    }


def _verify_frozen_shape() -> None:
    observed_columns = _read_columns()
    if observed_columns != _EXPECTED_COLUMNS:
        raise RuntimeError(
            "vector_external_docs_baseline_column_shape_mismatch:"
            f"{observed_columns!r}"
        )
    observed_indexes = _read_indexes()
    if observed_indexes != _EXPECTED_INDEXES:
        raise RuntimeError(
            "vector_external_docs_baseline_index_shape_mismatch:"
            f"{observed_indexes!r}"
        )


def upgrade() -> None:
    if not _table_exists():
        _create_frozen_table()
    _verify_frozen_shape()


def downgrade() -> None:
    # The baseline adopts a pre-existing host table. It is intentionally never
    # dropped by a ledger downgrade.
    pass
