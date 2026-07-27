"""Add exact terminal and enrollment lookup indexes.

Revision ID: 20260728020000
Revises: 20260727100000
Create Date: 2026-07-28 02:00:00.000000
"""

from alembic import op

from alembic_migrations.postgres import durable_outcome_lookup_v1

revision = "20260728020000"
down_revision = "20260727100000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    durable_outcome_lookup_v1.upgrade(op)


def downgrade() -> None:
    durable_outcome_lookup_v1.downgrade(op)
