"""Add parent_execution_id column to tasks table

Supports system-wide task grouping by allowing child tasks to reference
their parent execution context (batch operations, playbook sub-tasks, etc.).

Revision ID: 20260317170000
Revises: 20260310200000
Create Date: 2026-03-17 17:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "20260317170000"
down_revision = "20260310200000"
branch_labels = None
depends_on = None


def upgrade():
    # Add nullable column (safe for existing rows)
    op.add_column(
        "tasks",
        sa.Column("parent_execution_id", sa.String(), nullable=True),
    )
    # Index for grouped queries: WHERE parent_execution_id = ?
    op.create_index(
        "ix_tasks_parent_execution_id",
        "tasks",
        ["parent_execution_id"],
        if_not_exists=True,
    )


def downgrade():
    op.drop_index("ix_tasks_parent_execution_id", table_name="tasks")
    op.drop_column("tasks", "parent_execution_id")
