"""add_governance_tables

Revision ID: 20260130000004
Revises: 20260130000003
Create Date: 2026-01-30 00:00:04.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260130000004"
down_revision = "20260130000003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "governance_decisions",
        sa.Column("decision_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("execution_id", sa.String(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("layer", sa.String(), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("playbook_code", sa.String(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("decision_id"),
    )
    op.create_index(
        "idx_governance_decisions_workspace_timestamp",
        "governance_decisions",
        ["workspace_id", "timestamp"],
    )
    op.create_index(
        "idx_governance_decisions_execution",
        "governance_decisions",
        ["execution_id"],
    )
    op.create_index(
        "idx_governance_decisions_layer_approved",
        "governance_decisions",
        ["layer", "approved"],
    )

    op.create_table(
        "cost_usage",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("execution_id", sa.String(), nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("cost", sa.Float(), nullable=False),
        sa.Column("playbook_code", sa.String(), nullable=True),
        sa.Column("model_name", sa.String(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_cost_usage_workspace_date",
        "cost_usage",
        ["workspace_id", "date"],
    )
    op.create_index(
        "idx_cost_usage_execution",
        "cost_usage",
        ["execution_id"],
    )


def downgrade():
    op.drop_index(
        "idx_cost_usage_execution",
        table_name="cost_usage",
    )
    op.drop_index(
        "idx_cost_usage_workspace_date",
        table_name="cost_usage",
    )
    op.drop_table("cost_usage")

    op.drop_index(
        "idx_governance_decisions_layer_approved",
        table_name="governance_decisions",
    )
    op.drop_index(
        "idx_governance_decisions_execution",
        table_name="governance_decisions",
    )
    op.drop_index(
        "idx_governance_decisions_workspace_timestamp",
        table_name="governance_decisions",
    )
    op.drop_table("governance_decisions")
