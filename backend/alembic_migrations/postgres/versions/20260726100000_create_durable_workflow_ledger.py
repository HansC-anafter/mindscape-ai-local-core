"""Create the durable product-semantic workflow v1 ledger.

Revision ID: 20260726100000
Revises: 20260725140000
Create Date: 2026-07-26 10:00:00.000000
"""

from alembic import op

from alembic_migrations.postgres import durable_workflow_v1

revision = "20260726100000"
down_revision = "20260725140000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    durable_workflow_v1.upgrade(op)


def downgrade() -> None:
    durable_workflow_v1.downgrade(op)
