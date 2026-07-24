"""Preserve a removed capability revision as a no-op graph anchor.

Revision ID: 20260415000000
Revises: 20260328003000
Create Date: 2026-04-15 00:00:00.000000

The canonical schema owner is the ``ig`` capability pack. Local Core owns only
this no-op graph anchor and must not treat it as a competing schema migration.
"""

from alembic import op


revision = "20260415000000"
down_revision = "20260328003000"
branch_labels = None
depends_on = None
pack_owner_capability = "ig"


def upgrade() -> None:
    op.execute("SELECT 1")


def downgrade() -> None:
    op.execute("SELECT 1")
