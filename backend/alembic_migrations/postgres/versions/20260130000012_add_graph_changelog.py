"""Add graph_changelog table for version control

Revision ID: 20260130000012
Revises: 20260130000011
Create Date: 2026-01-30 06:39:00.000000

This table implements Event Sourcing for the Mindscape Graph,
recording every atomic operation for undo/redo and time-travel support.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260130000012"
down_revision = "20260130000011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create graph_changelog table for version control
    op.create_table(
        "graph_changelog",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            comment="Monotonically increasing version per workspace",
        ),
        sa.Column(
            "operation",
            sa.String(length=50),
            nullable=False,
            comment="create_node, update_node, delete_node, create_edge, delete_edge, update_overlay",
        ),
        sa.Column(
            "target_type",
            sa.String(length=20),
            nullable=False,
            comment="node, edge, overlay",
        ),
        sa.Column(
            "target_id",
            sa.String(length=100),
            nullable=False,
            comment="ID of the affected node/edge",
        ),
        sa.Column(
            "before_state",
            sa.Text(),
            nullable=True,
            comment="JSON: state before change (for undo)",
        ),
        sa.Column(
            "after_state",
            sa.Text(),
            nullable=False,
            comment="JSON: state after change",
        ),
        sa.Column(
            "actor",
            sa.String(length=20),
            nullable=False,
            comment="user, llm, system, playbook",
        ),
        sa.Column(
            "actor_context",
            sa.Text(),
            nullable=True,
            comment="Additional context: LLM prompt, conversation ID, etc.",
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
            comment="pending, applied, rejected, undone",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "applied_at",
            sa.DateTime(),
            nullable=True,
            comment="When the change was approved and applied",
        ),
        sa.Column(
            "applied_by",
            sa.String(length=36),
            nullable=True,
            comment="Profile ID of the approver",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id", "version", name="uq_changelog_workspace_version"
        ),
        sa.CheckConstraint(
            "actor IN ('user', 'llm', 'system', 'playbook')",
            name="ck_changelog_actor",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'applied', 'rejected', 'undone')",
            name="ck_changelog_status",
        ),
        sa.CheckConstraint(
            "operation IN ('create_node', 'update_node', 'delete_node', "
            "'create_edge', 'update_edge', 'delete_edge', "
            "'update_overlay', 'batch')",
            name="ck_changelog_operation",
        ),
        sa.CheckConstraint(
            "target_type IN ('node', 'edge', 'overlay', 'batch')",
            name="ck_changelog_target_type",
        ),
    )

    # Indexes for efficient querying
    op.create_index(
        "idx_changelog_workspace",
        "graph_changelog",
        ["workspace_id"],
    )
    op.create_index(
        "idx_changelog_status",
        "graph_changelog",
        ["status"],
    )
    op.create_index(
        "idx_changelog_version",
        "graph_changelog",
        ["workspace_id", "version"],
    )
    op.create_index(
        "idx_changelog_actor",
        "graph_changelog",
        ["actor"],
    )
    op.create_index(
        "idx_changelog_pending",
        "graph_changelog",
        ["workspace_id", "status"],
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("idx_changelog_pending", table_name="graph_changelog")
    op.drop_index("idx_changelog_actor", table_name="graph_changelog")
    op.drop_index("idx_changelog_version", table_name="graph_changelog")
    op.drop_index("idx_changelog_status", table_name="graph_changelog")
    op.drop_index("idx_changelog_workspace", table_name="graph_changelog")
    op.drop_table("graph_changelog")
