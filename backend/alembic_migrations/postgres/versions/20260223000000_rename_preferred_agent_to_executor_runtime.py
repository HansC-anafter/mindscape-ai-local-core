"""rename preferred_agent to executor_runtime

Revision ID: 20260223000000
Revises: 20260222000005
Create Date: 2026-02-23

Part of Phase 0 P2-a terminology alignment:
  AgentSpec/AgentInstance framework separates "agent identity" from "runtime".
  The `preferred_agent` column stores a runtime adapter ID, not an agent identity,
  so rename it to `executor_runtime` for semantic accuracy.
"""

from alembic import op

# revision identifiers
revision = "20260223000000"
down_revision = "20260222000005"
branch_labels = None
depends_on = None


def upgrade():
    # Check if the old column exists before attempting rename
    from sqlalchemy import inspect

    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("workspaces")]

    if "preferred_agent" in columns and "executor_runtime" not in columns:
        op.alter_column(
            "workspaces",
            "preferred_agent",
            new_column_name="executor_runtime",
        )
    elif "executor_runtime" in columns:
        # Already renamed, nothing to do
        pass
    else:
        # Column doesn't exist yet; will be created by a later migration
        pass


def downgrade():
    from sqlalchemy import inspect

    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("workspaces")]

    if "executor_runtime" in columns and "preferred_agent" not in columns:
        op.alter_column(
            "workspaces",
            "executor_runtime",
            new_column_name="preferred_agent",
        )
