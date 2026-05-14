"""Add task summary projection control fields.

Revision ID: 20260514114500
Revises: 20260514113000
Create Date: 2026-05-14 11:45:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260514114500"
down_revision = "20260514113000"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "task_summary_projection",
        sa.Column("next_eligible_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "task_summary_projection",
        sa.Column("blocked_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "task_summary_projection",
        sa.Column("frontier_state", sa.Text(), nullable=True),
    )
    op.add_column(
        "task_summary_projection",
        sa.Column("frontier_enqueued_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("task_summary_projection", "frontier_enqueued_at")
    op.drop_column("task_summary_projection", "frontier_state")
    op.drop_column("task_summary_projection", "blocked_reason")
    op.drop_column("task_summary_projection", "next_eligible_at")
