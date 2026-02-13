"""Add mindscape_personal table

Revision ID: 20260127000006
Revises: 20260127000005
Create Date: 2026-01-27

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260127000006"
down_revision: Union[str, None] = "20260127000005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create mindscape_personal table."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("mindscape_personal"):
        return

    op.create_table(
        "mindscape_personal",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("seed_type", sa.String(64), nullable=False),
        sa.Column("seed_text", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(64), nullable=True),
        sa.Column("source_id", sa.String(64), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True, server_default="1.0"),
        sa.Column("weight", sa.Float(), nullable=True, server_default="1.0"),
        sa.Column("embedding", sa.Text(), nullable=True),
        sa.Column("metadata", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    # Create indexes
    op.create_index("ix_mindscape_personal_user_id", "mindscape_personal", ["user_id"])
    op.create_index(
        "ix_mindscape_personal_seed_type", "mindscape_personal", ["seed_type"]
    )


def downgrade() -> None:
    """Drop mindscape_personal table."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("mindscape_personal"):
        return

    existing_columns = {col["name"] for col in inspector.get_columns("mindscape_personal")}
    # Skip dropping the legacy table shape created by the initial bootstrap migration.
    if "seed_type" not in existing_columns:
        return

    existing_indexes = {idx["name"] for idx in inspector.get_indexes("mindscape_personal")}
    if "ix_mindscape_personal_seed_type" in existing_indexes:
        op.drop_index("ix_mindscape_personal_seed_type", table_name="mindscape_personal")
    if "ix_mindscape_personal_user_id" in existing_indexes:
        op.drop_index("ix_mindscape_personal_user_id", table_name="mindscape_personal")
    op.drop_table("mindscape_personal")
