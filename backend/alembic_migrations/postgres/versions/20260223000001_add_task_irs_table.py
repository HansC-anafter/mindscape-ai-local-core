"""Add task_irs table

Revision ID: 20260223000001
Revises: 20260223000000
Create Date: 2026-02-23

Migrates TaskIR persistence from SQLite to PostgreSQL.
Uses native JSONB for phases, artifacts, and metadata columns.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "20260223000001"
down_revision = "20260223000000"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "task_irs",
        sa.Column("task_id", sa.Text(), primary_key=True),
        sa.Column("intent_instance_id", sa.Text(), nullable=False),
        sa.Column("workspace_id", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.Text(), nullable=False),
        sa.Column("current_phase", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "phases",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "artifacts",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_checkpoint_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index("idx_task_irs_workspace", "task_irs", ["workspace_id"])
    op.create_index("idx_task_irs_intent", "task_irs", ["intent_instance_id"])
    op.create_index("idx_task_irs_status", "task_irs", ["status"])
    op.create_index("idx_task_irs_current_phase", "task_irs", ["current_phase"])


def downgrade():
    op.drop_index("idx_task_irs_current_phase", table_name="task_irs")
    op.drop_index("idx_task_irs_status", table_name="task_irs")
    op.drop_index("idx_task_irs_intent", table_name="task_irs")
    op.drop_index("idx_task_irs_workspace", table_name="task_irs")
    op.drop_table("task_irs")
