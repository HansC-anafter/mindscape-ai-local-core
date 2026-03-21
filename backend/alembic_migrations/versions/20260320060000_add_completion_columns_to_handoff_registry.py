"""Add execution_id, artifact_id, completed_at to handoff_registry.

- execution_id: links to the execution that fulfilled this dispatch
- artifact_id: links to the artifact produced by landing
- completed_at: timestamp when dispatch was marked completed

Revision ID: 20260320060000
Revises: 20260320050000
Create Date: 2026-03-20 06:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "20260320060000"
down_revision = "20260320050000"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "handoff_registry",
        sa.Column("execution_id", sa.String(), nullable=True),
    )
    op.add_column(
        "handoff_registry",
        sa.Column("artifact_id", sa.String(), nullable=True),
    )
    op.add_column(
        "handoff_registry",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_handoff_registry_execution_id",
        "handoff_registry",
        ["execution_id"],
    )


def downgrade():
    op.drop_index("ix_handoff_registry_execution_id", table_name="handoff_registry")
    op.drop_column("handoff_registry", "completed_at")
    op.drop_column("handoff_registry", "artifact_id")
    op.drop_column("handoff_registry", "execution_id")
