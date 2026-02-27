"""Add contact fields to ig_accounts_flat

Revision ID: 20260216000000
Revises: 20260210025800
Create Date: 2026-02-16 00:00:00.000000

Adds public_email, public_phone_number, and business_address_json columns
for contact information extracted from Instagram profile pages.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260216000000"
down_revision = "20260210025800"
branch_labels = None
depends_on = None


def _column_exists(conn, column_name: str) -> bool:
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name='ig_accounts_flat' AND column_name=:col"
        ),
        {"col": column_name},
    ).fetchone()
    return result is not None


def upgrade():
    conn = op.get_bind()

    if not _column_exists(conn, "public_email"):
        op.add_column(
            "ig_accounts_flat",
            sa.Column("public_email", sa.String(255), nullable=True),
        )

    if not _column_exists(conn, "public_phone_number"):
        op.add_column(
            "ig_accounts_flat",
            sa.Column("public_phone_number", sa.String(64), nullable=True),
        )

    if not _column_exists(conn, "business_address_json"):
        op.add_column(
            "ig_accounts_flat",
            sa.Column("business_address_json", sa.Text(), nullable=True),
        )


def downgrade():
    op.drop_column("ig_accounts_flat", "business_address_json")
    op.drop_column("ig_accounts_flat", "public_phone_number")
    op.drop_column("ig_accounts_flat", "public_email")
