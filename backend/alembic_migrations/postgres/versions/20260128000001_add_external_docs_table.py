"""Add external_docs table for RAG

Revision ID: 20260128000001
Revises: 20260127000006
Create Date: 2026-01-28

Creates external_docs table for storing external document embeddings
used by RAG (Retrieval-Augmented Generation) from local folders.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260128000001"
down_revision = "20260127000006"
branch_labels = None
depends_on = None


def upgrade():
    """Create external_docs table."""
    # Ensure pgvector extension exists
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("external_docs"):
        return

    op.create_table(
        "external_docs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("source_app", sa.String(64), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", sa.dialects.postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column(
            "metadata", sa.dialects.postgresql.JSONB(), nullable=True, default={}
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "source_app", "title", name="uq_external_docs_user_source_title"
        ),
    )

    # Use raw SQL to create vector column since SQLAlchemy doesn't support it natively
    op.execute(
        "ALTER TABLE external_docs ALTER COLUMN embedding TYPE vector(768) USING embedding::vector(768)"
    )

    op.create_index("idx_external_docs_user", "external_docs", ["user_id"])
    op.create_index("idx_external_docs_source", "external_docs", ["source_app"])


def downgrade():
    """Drop external_docs table."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("external_docs"):
        return

    existing_columns = {col["name"] for col in inspector.get_columns("external_docs")}
    # Skip dropping the legacy table shape created by the initial bootstrap migration.
    if "source_id" in existing_columns:
        return

    existing_indexes = {idx["name"] for idx in inspector.get_indexes("external_docs")}
    if "idx_external_docs_source" in existing_indexes:
        op.drop_index("idx_external_docs_source", table_name="external_docs")
    if "idx_external_docs_user" in existing_indexes:
        op.drop_index("idx_external_docs_user", table_name="external_docs")
    op.drop_table("external_docs")
