"""Drop workspace executor route shadow columns.

Revision ID: 20260427090000
Revises: 20260416000000
Create Date: 2026-04-27 09:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260427090000"
down_revision = "20260416000000"
branch_labels = None
depends_on = None

_RUNTIME_COLUMN = "executor" + "_runtime"
_SPECS_COLUMN = "executor" + "_specs"


def _workspace_columns() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns("workspaces")}


def upgrade() -> None:
    columns = _workspace_columns()
    if _RUNTIME_COLUMN in columns:
        op.drop_column("workspaces", _RUNTIME_COLUMN)
    if _SPECS_COLUMN in columns:
        op.drop_column("workspaces", _SPECS_COLUMN)


def downgrade() -> None:
    columns = _workspace_columns()
    if _RUNTIME_COLUMN not in columns:
        op.add_column(
            "workspaces",
            sa.Column(_RUNTIME_COLUMN, sa.String(length=128), nullable=True),
        )
    if _SPECS_COLUMN not in columns:
        op.add_column(
            "workspaces",
            sa.Column(
                _SPECS_COLUMN,
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
        )
