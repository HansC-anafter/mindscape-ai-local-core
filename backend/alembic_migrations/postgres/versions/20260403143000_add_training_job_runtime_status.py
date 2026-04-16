"""add character training job runtime status

Revision ID: 20260403143000
Revises: 20260403110000
Create Date: 2026-04-03 14:30:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260403143000"
down_revision: Union[str, None] = "20260403110000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(inspector, table_name: str, column_name: str) -> bool:
    columns = inspector.get_columns(table_name)
    return any(column["name"] == column_name for column in columns)


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if not _column_exists(inspector, "character_training_jobs", "runtime_status_json"):
        op.add_column(
            "character_training_jobs",
            sa.Column("runtime_status_json", postgresql.JSONB(), nullable=True),
        )


def downgrade() -> None:
    pass
