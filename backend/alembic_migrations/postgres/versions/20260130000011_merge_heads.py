"""Merge multiple heads into single head

Revision ID: 20260130000011
Revises: 20260128000001, 20260129100000, 20260130000010
Create Date: 2026-01-30 06:16:00.000000

This migration merges three branch heads:
- 20260128000001_add_external_docs_table
- 20260129100000_extend_project_id_column_length
- 20260130000010_add_mindscape_overlays
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260130000011"
down_revision = ("20260128000001", "20260129100000", "20260130000010")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This is a merge migration, no schema changes needed
    pass


def downgrade() -> None:
    # This is a merge migration, no schema changes needed
    pass
