"""Preserve a removed capability revision as a no-op graph anchor.

Revision ID: 20260323010000
Revises: 20260322020000
Create Date: 2026-03-23 01:00:00.000000
"""

from alembic import op


revision = "20260323010000"
down_revision = "20260322020000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SELECT 1")


def downgrade() -> None:
    op.execute("SELECT 1")
