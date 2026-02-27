"""Add project_id column to intents table

Revision ID: 20260228000000
Revises: 20260226000000
Create Date: 2026-02-28

Store code already references intents.project_id for project-scoped
filtering, but no migration ever added the column.
Ref: meeting_system_full_investigation.md §三 問題二
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect

revision = "20260228000000"
down_revision = "20260226000000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Hotfix already added project_id via ALTER TABLE.
    # Use inspect to check existence for idempotency.
    conn = op.get_bind()
    inspector = sa_inspect(conn)
    columns = [col["name"] for col in inspector.get_columns("intents")]

    if "project_id" not in columns:
        op.add_column(
            "intents",
            sa.Column("project_id", sa.String(128), nullable=True),
        )

    # Index (IF NOT EXISTS is safe)
    op.create_index(
        "ix_intents_project",
        "intents",
        ["project_id"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_intents_project", table_name="intents")
    op.drop_column("intents", "project_id")
