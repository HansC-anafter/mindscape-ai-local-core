"""Add compact task inputs to task summary projection.

Revision ID: 20260529123000
Revises: 20260529110000
Create Date: 2026-05-29 12:30:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260529123000"
down_revision = "20260529110000"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "task_summary_projection",
        sa.Column(
            "compact_inputs",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade():
    op.drop_column("task_summary_projection", "compact_inputs")
