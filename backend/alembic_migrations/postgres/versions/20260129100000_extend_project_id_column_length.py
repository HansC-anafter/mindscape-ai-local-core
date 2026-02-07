"""Extend project_id and workspace_id column lengths from VARCHAR(36) to VARCHAR(128)

Revision ID: 20260129100000
Revises: 20260127000001
Create Date: 2026-01-29

Fix: project_id values like 'content_campaign_20251215_134931_c9b794db' (42 chars)
exceed the VARCHAR(36) limit, causing StringDataRightTruncation errors.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260129100000"
down_revision = "20260127000007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Extend project_id and related ID columns from VARCHAR(36) to VARCHAR(128)."""

    # mind_events table - the main issue causing message write failures
    op.alter_column(
        "mind_events",
        "project_id",
        existing_type=sa.String(36),
        type_=sa.String(128),
        existing_nullable=True,
    )

    # baseline_events table
    op.alter_column(
        "baseline_events",
        "project_id",
        existing_type=sa.String(36),
        type_=sa.String(128),
        existing_nullable=True,
    )
    op.alter_column(
        "baseline_events",
        "workspace_id",
        existing_type=sa.String(36),
        type_=sa.String(128),
        existing_nullable=False,
    )

    # tool_slot_mappings table
    op.alter_column(
        "tool_slot_mappings",
        "project_id",
        existing_type=sa.String(36),
        type_=sa.String(128),
        existing_nullable=True,
    )

    # web_generation_baselines table
    op.alter_column(
        "web_generation_baselines",
        "project_id",
        existing_type=sa.String(36),
        type_=sa.String(128),
        existing_nullable=True,
    )

    # project_phases table
    op.alter_column(
        "project_phases",
        "project_id",
        existing_type=sa.String(36),
        type_=sa.String(128),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Revert project_id columns back to VARCHAR(36)."""

    op.alter_column(
        "project_phases",
        "project_id",
        existing_type=sa.String(128),
        type_=sa.String(36),
        existing_nullable=False,
    )

    op.alter_column(
        "web_generation_baselines",
        "project_id",
        existing_type=sa.String(128),
        type_=sa.String(36),
        existing_nullable=True,
    )

    op.alter_column(
        "tool_slot_mappings",
        "project_id",
        existing_type=sa.String(128),
        type_=sa.String(36),
        existing_nullable=True,
    )

    op.alter_column(
        "baseline_events",
        "workspace_id",
        existing_type=sa.String(128),
        type_=sa.String(36),
        existing_nullable=False,
    )
    op.alter_column(
        "baseline_events",
        "project_id",
        existing_type=sa.String(128),
        type_=sa.String(36),
        existing_nullable=True,
    )

    op.alter_column(
        "mind_events",
        "project_id",
        existing_type=sa.String(128),
        type_=sa.String(36),
        existing_nullable=True,
    )
