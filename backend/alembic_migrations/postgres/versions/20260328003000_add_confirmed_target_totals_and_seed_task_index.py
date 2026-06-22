"""Keep pack-owned seed projections out of core migrations.

Revision ID: 20260328003000
Revises: 20260323010000
Create Date: 2026-03-28 00:30:00.000000
"""

from alembic import op


revision = "20260328003000"
down_revision = "20260323010000"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SELECT 1")


def downgrade():
    op.execute("SELECT 1")
