"""Preserve the historical revision without restoring pack-owned schema.

Revision ID: 20260311000000
Revises: 20260310183000
Create Date: 2026-03-11 00:00:00.000000

The original revision created Cloud capability-pack tables and was intentionally
removed by commit 56fb1e54. A surviving core revision still names this ID as its
parent, so this no-op tombstone repairs the Alembic graph while preserving the
host/pack database ownership boundary.

The canonical schema owner is the ``ig`` capability pack. Local Core owns only
this no-op graph anchor and must not treat it as a competing schema migration.
"""

from alembic import op


revision = "20260311000000"
down_revision = "20260310183000"
branch_labels = None
depends_on = None
pack_owner_capability = "ig"


def upgrade() -> None:
    op.execute("SELECT 1")


def downgrade() -> None:
    op.execute("SELECT 1")
