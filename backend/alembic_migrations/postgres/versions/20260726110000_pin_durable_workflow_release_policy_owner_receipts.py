"""Pin exact owner receipt and trusted-registry identity on release policy.

Revision ID: 20260726110000
Revises: 20260726100000
Create Date: 2026-07-26 11:00:00.000000
"""

from alembic import op

from alembic_migrations.postgres import (
    durable_workflow_release_policy_owner_receipts_v1,
)

revision = "20260726110000"
down_revision = "20260726100000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    durable_workflow_release_policy_owner_receipts_v1.upgrade(op)


def downgrade() -> None:
    durable_workflow_release_policy_owner_receipts_v1.downgrade(op)
