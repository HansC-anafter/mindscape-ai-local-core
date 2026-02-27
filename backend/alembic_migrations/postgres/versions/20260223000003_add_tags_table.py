"""Add tags table for entities store migration.

Revision ID: 20260223000003
Revises: 20260223000002
Create Date: 2026-02-23

The entities and entity_tags tables already exist from prior migrations.
This adds the missing tags table required by the EntitiesStore.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "20260223000003"
down_revision = "20260223000002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tags",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("profile_id", sa.String(64), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("color", sa.String(20), nullable=True),
        sa.Column("metadata", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=True,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_tags_profile", "tags", ["profile_id"])
    op.create_index("idx_tags_category", "tags", ["category"])


def downgrade():
    op.drop_index("idx_tags_category", table_name="tags")
    op.drop_index("idx_tags_profile", table_name="tags")
    op.drop_table("tags")
