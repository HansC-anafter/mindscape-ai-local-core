"""Index the canonical title-and-content lexical document.

Revision ID: 20260729010000
Revises: 20260727050000
Create Date: 2026-07-29
"""

from __future__ import annotations

from alembic import op


revision = "20260729010000"
down_revision = "20260727050000"
branch_labels = None
depends_on = None

INDEX_NAME = "idx_external_docs_lexical_simple"


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            f"""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME}
            ON external_docs
            USING gin ((
                setweight(
                    to_tsvector(
                        'simple'::regconfig,
                        COALESCE(title, '')
                    ),
                    'A'
                )
                ||
                setweight(
                    to_tsvector(
                        'simple'::regconfig,
                        COALESCE(content, '')
                    ),
                    'D'
                )
            ))
            """
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME}"
        )
