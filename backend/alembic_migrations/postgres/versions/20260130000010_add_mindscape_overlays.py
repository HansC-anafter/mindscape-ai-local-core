"""Add mindscape_overlays table for graph overlay persistence

Revision ID: 20260130000010
Revises: 20260130000009
Create Date: 2026-01-30 06:15:00.000000

This table stores the overlay data for the Mindscape Graph visualization,
including node positions, collapsed states, viewport settings, and manual
nodes/edges created by users.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260130000010"
down_revision = "20260130000009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create mindscape_overlays table
    op.create_table(
        "mindscape_overlays",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "scope_type",
            sa.String(length=50),
            nullable=False,
            comment="Scope type: 'workspace' or 'workspace_group'",
        ),
        sa.Column(
            "scope_id",
            sa.String(length=36),
            nullable=False,
            comment="Workspace or workspace group ID",
        ),
        sa.Column(
            "data",
            sa.Text(),
            nullable=False,
            comment="JSON-serialized GraphOverlay data",
        ),
        sa.Column(
            "version",
            sa.Integer(),
            server_default="1",
            nullable=False,
            comment="Version number for cache invalidation",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "scope_type", "scope_id", name="uq_mindscape_overlays_scope"
        ),
        sa.CheckConstraint(
            "scope_type IN ('workspace', 'workspace_group')",
            name="ck_mindscape_overlays_scope_type",
        ),
    )

    # Create index for efficient lookup by scope
    op.create_index(
        "idx_mindscape_overlays_scope",
        "mindscape_overlays",
        ["scope_type", "scope_id"],
    )

    # Create index for updated_at (for cache management)
    op.create_index(
        "idx_mindscape_overlays_updated",
        "mindscape_overlays",
        ["updated_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_mindscape_overlays_updated", table_name="mindscape_overlays")
    op.drop_index("idx_mindscape_overlays_scope", table_name="mindscape_overlays")
    op.drop_table("mindscape_overlays")
