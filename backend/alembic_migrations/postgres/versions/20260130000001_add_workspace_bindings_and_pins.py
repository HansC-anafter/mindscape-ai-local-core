"""add_workspace_bindings_and_pins

Revision ID: 20260130000001
Revises: 20260130000000
Create Date: 2026-01-30 00:00:01.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260130000001"
down_revision = "20260130000000"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "workspace_resource_bindings",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("resource_type", sa.String(), nullable=False),
        sa.Column("resource_id", sa.String(), nullable=False),
        sa.Column("access_mode", sa.String(), nullable=False, server_default="read"),
        sa.Column("overrides", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_workspace_resource_bindings_workspace_type",
        "workspace_resource_bindings",
        ["workspace_id", "resource_type"],
    )
    op.create_index(
        "idx_workspace_resource_bindings_workspace_resource",
        "workspace_resource_bindings",
        ["workspace_id", "resource_type", "resource_id"],
    )
    op.create_index(
        "idx_workspace_resource_bindings_resource",
        "workspace_resource_bindings",
        ["resource_type", "resource_id"],
    )

    op.create_table(
        "workspace_pinned_playbooks",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("playbook_code", sa.String(), nullable=False),
        sa.Column("pinned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pinned_by", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_workspace_pinned_playbooks_workspace",
        "workspace_pinned_playbooks",
        ["workspace_id"],
    )
    op.create_index(
        "idx_workspace_pinned_playbooks_playbook",
        "workspace_pinned_playbooks",
        ["playbook_code"],
    )
    op.create_index(
        "idx_workspace_pinned_playbooks_workspace_playbook",
        "workspace_pinned_playbooks",
        ["workspace_id", "playbook_code"],
        unique=True,
    )


def downgrade():
    op.drop_index(
        "idx_workspace_pinned_playbooks_workspace_playbook",
        table_name="workspace_pinned_playbooks",
    )
    op.drop_index(
        "idx_workspace_pinned_playbooks_playbook",
        table_name="workspace_pinned_playbooks",
    )
    op.drop_index(
        "idx_workspace_pinned_playbooks_workspace",
        table_name="workspace_pinned_playbooks",
    )
    op.drop_table("workspace_pinned_playbooks")

    op.drop_index(
        "idx_workspace_resource_bindings_resource",
        table_name="workspace_resource_bindings",
    )
    op.drop_index(
        "idx_workspace_resource_bindings_workspace_resource",
        table_name="workspace_resource_bindings",
    )
    op.drop_index(
        "idx_workspace_resource_bindings_workspace_type",
        table_name="workspace_resource_bindings",
    )
    op.drop_table("workspace_resource_bindings")
