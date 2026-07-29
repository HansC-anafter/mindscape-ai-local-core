"""Add resource-level agent narrowing masks and immutable audit.

Revision ID: 20260727036000
Revises: 20260727035000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision = "20260727036000"
down_revision = "20260727035000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_resource_agent_masks",
        sa.Column("mask_id", sa.Text(), primary_key=True),
        sa.Column(
            "knowledge_resource_id",
            sa.Text(),
            sa.ForeignKey(
                "knowledge_resources.knowledge_resource_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("agent_role", sa.Text(), nullable=False),
        sa.Column("effect", sa.Text(), nullable=False),
        sa.Column("policy_revision", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "effect IN ('allow', 'deny')",
            name="ck_knowledge_agent_mask_effect",
        ),
        sa.UniqueConstraint(
            "knowledge_resource_id",
            "agent_role",
            "effect",
            name="uq_knowledge_resource_agent_mask",
        ),
    )
    op.create_index(
        "idx_knowledge_agent_mask_lookup",
        "knowledge_resource_agent_masks",
        ["knowledge_resource_id", "agent_role", "effect"],
    )
    op.create_table(
        "knowledge_agent_mask_audit_log",
        sa.Column("mutation_id", sa.Text(), primary_key=True),
        sa.Column(
            "knowledge_resource_id",
            sa.Text(),
            sa.ForeignKey(
                "knowledge_resources.knowledge_resource_id",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("actor_user_id", sa.Text(), nullable=False),
        sa.Column("principal_context_hash", sa.Text(), nullable=False),
        sa.Column("old_policy_revision", sa.Text()),
        sa.Column("new_policy_revision", sa.Text(), nullable=False),
        sa.Column("normalized_masks", JSONB, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index(
        "idx_knowledge_agent_mask_audit_resource",
        "knowledge_agent_mask_audit_log",
        ["knowledge_resource_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("knowledge_agent_mask_audit_log")
    op.drop_table("knowledge_resource_agent_masks")
