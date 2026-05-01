"""Drop the legacy workspace-level LLM detour column.

Revision ID: 20260416000000
Revises: 20260415000001
Create Date: 2026-04-27 07:30:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "20260416000000"
down_revision = "20260415000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("workspaces")}
    legacy_column = "fallback" + "_model"
    if legacy_column in columns:
        op.drop_column("workspaces", legacy_column)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("workspaces")}
    legacy_column = "fallback" + "_model"
    if legacy_column not in columns:
        op.add_column(
            "workspaces",
            sa.Column(
                legacy_column,
                sa.String(length=128),
                nullable=True,
                comment="Legacy workspace-level LLM detour model name.",
            ),
        )
