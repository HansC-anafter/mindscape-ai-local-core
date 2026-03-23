"""
Migration: add storyboard_manifest to direction_artifact_type enum.

Revision ID: 20260322000001
Create Date: 2026-03-22
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260322000001"
down_revision = "001_create_direction_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE direction_artifact_type "
        "ADD VALUE IF NOT EXISTS 'storyboard_manifest'"
    )


def downgrade() -> None:
    # PostgreSQL enums do not support dropping values safely in-place.
    pass
