"""Add embedding state columns to pack activation state

Revision ID: 20260321190000
Revises: 20260321143000
Create Date: 2026-03-21 19:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260321190000"
down_revision = "20260321143000"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "pack_activation_state",
        sa.Column(
            "embedding_state",
            sa.String(),
            nullable=False,
            server_default="unknown",
        ),
    )
    op.add_column(
        "pack_activation_state",
        sa.Column("embedding_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "pack_activation_state",
        sa.Column("embeddings_updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.execute(
        """
        UPDATE pack_activation_state
        SET embedding_state = CASE
            WHEN enabled = false THEN 'disabled'
            ELSE 'unknown'
        END
        WHERE embedding_state = 'unknown'
        """
    )


def downgrade():
    op.drop_column("pack_activation_state", "embeddings_updated_at")
    op.drop_column("pack_activation_state", "embedding_error")
    op.drop_column("pack_activation_state", "embedding_state")
