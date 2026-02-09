"""Add is_private column to ig_accounts_flat

Revision ID: 20260210025800
Revises: 20260124170000
Create Date: 2026-02-10 02:58:00.000000

Adds is_private boolean column for tracking whether an Instagram account is private.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260210025800"
down_revision = "20260124170000"
branch_labels = None
depends_on = None


def upgrade():
    # Add is_private column
    op.add_column(
        "ig_accounts_flat", sa.Column("is_private", sa.Boolean(), nullable=True)
    )


def downgrade():
    op.drop_column("ig_accounts_flat", "is_private")
