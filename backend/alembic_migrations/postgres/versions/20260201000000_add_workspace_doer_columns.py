"""Add workspace doer columns for agent selection persistence

Revision ID: 20260201000000
Revises: 20260130000012
Create Date: 2026-02-01 19:55:00.000000

This migration adds columns to support the Doer/Agent Runner feature:
- preferred_agent: The selected agent ID from the agent registry
- sandbox_config: JSON configuration for sandbox settings
- doer_fallback_to_mindscape: Whether to fallback to Mindscape LLM if agent fails
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260201000000"
down_revision = "20260130000012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add preferred_agent column
    op.add_column(
        "workspaces",
        sa.Column(
            "preferred_agent",
            sa.String(length=128),
            nullable=True,
            comment="Preferred agent ID for workspace from agent registry",
        ),
    )

    # Add sandbox_config column
    op.add_column(
        "workspaces",
        sa.Column(
            "sandbox_config",
            sa.Text(),
            nullable=True,
            comment="JSON configuration for sandbox settings when using external agents",
        ),
    )

    # Add doer_fallback_to_mindscape column
    op.add_column(
        "workspaces",
        sa.Column(
            "doer_fallback_to_mindscape",
            sa.Boolean(),
            server_default="true",
            nullable=True,
            comment="If preferred_agent fails, fallback to Mindscape LLM",
        ),
    )


def downgrade() -> None:
    op.drop_column("workspaces", "doer_fallback_to_mindscape")
    op.drop_column("workspaces", "sandbox_config")
    op.drop_column("workspaces", "preferred_agent")
