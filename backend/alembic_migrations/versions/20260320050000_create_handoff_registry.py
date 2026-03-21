"""Create handoff_registry table for dispatch idempotency.

Each dispatch attempt registers its unique idempotency_key before
execution. The UNIQUE constraint prevents duplicate dispatches at the
database level.

Revision ID: 20260320050000
Revises: 20260317170000
Create Date: 2026-03-20 05:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "20260320050000"
down_revision = "20260317170000"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "handoff_registry",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("task_ir_id", sa.String(), nullable=False),
        sa.Column("phase_id", sa.String(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(), nullable=False, server_default="dispatched"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "idempotency_key", name="uq_handoff_registry_idempotency_key"
        ),
    )
    op.create_index(
        "ix_handoff_registry_task_ir_id",
        "handoff_registry",
        ["task_ir_id"],
    )


def downgrade():
    op.drop_index("ix_handoff_registry_task_ir_id", table_name="handoff_registry")
    op.drop_table("handoff_registry")
