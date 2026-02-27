"""Add is_private column to ig_accounts_flat

Revision ID: 20260210025800
Revises: 20260210000002
Create Date: 2026-02-10 02:58:00.000000

Adds is_private boolean column for tracking whether an Instagram account is private.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260210025800"
down_revision = "20260210000002"
branch_labels = None
depends_on = None


def upgrade():
    # Add is_private column (idempotent: skip if already exists)
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name='ig_accounts_flat' AND column_name='is_private'"
        )
    ).fetchone()
    if not result:
        op.add_column(
            "ig_accounts_flat", sa.Column("is_private", sa.Boolean(), nullable=True)
        )


def downgrade():
    op.drop_column("ig_accounts_flat", "is_private")
