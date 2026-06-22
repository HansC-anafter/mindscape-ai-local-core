"""Keep pack-owned task handle indexes out of core migrations.

Revision ID: 20260415000001
Revises: 20260415000000
Create Date: 2026-04-15 12:30:00.000000
"""

from alembic import op


revision = "20260415000001"
down_revision = "20260415000000"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SELECT 1")


def downgrade():
    op.execute("SELECT 1")
