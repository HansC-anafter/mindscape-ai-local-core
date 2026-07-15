"""Add source ledger, knowledge projections, and group synthesis receipts.

Revision ID: 20260715130000
Revises: 20260715123000
Create Date: 2026-07-15 13:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260715130000"
down_revision = "20260715123000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_source_states",
        sa.Column("source_instance_id", sa.String(length=128), primary_key=True),
        sa.Column("owner_type", sa.String(length=64), nullable=False),
        sa.Column("owner_id", sa.String(length=128), nullable=False),
        sa.Column("binding_id", sa.String(length=128), nullable=True),
        sa.Column("cursor", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("checkpoint", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("last_evidence_revision", sa.String(length=256), nullable=True),
        sa.Column("last_result", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("visibility", sa.String(length=32), nullable=False, server_default="private"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "visibility IN ('private', 'workspace', 'group')",
            name="chk_knowledge_source_state_visibility",
        ),
    )
    op.create_index(
        "idx_knowledge_source_states_owner",
        "knowledge_source_states",
        ["owner_type", "owner_id", "updated_at"],
    )

    op.create_table(
        "knowledge_source_intakes",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("source_instance_id", sa.String(length=128), nullable=False),
        sa.Column("source_revision", sa.String(length=256), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("evidence_type", sa.String(length=64), nullable=False),
        sa.Column("evidence_id", sa.String(length=256), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(
            ["source_instance_id"],
            ["knowledge_source_states.source_instance_id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "source_instance_id",
            "source_revision",
            "content_hash",
            name="uq_knowledge_source_intake_revision",
        ),
    )
    op.create_index(
        "idx_knowledge_source_intakes_source_created",
        "knowledge_source_intakes",
        ["source_instance_id", "created_at"],
    )

    op.create_table(
        "knowledge_projection_manifests",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("projection_type", sa.String(length=64), nullable=False),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("scope_id", sa.String(length=128), nullable=False),
        sa.Column("topology_snapshot_id", sa.String(length=64), nullable=True),
        sa.Column("input_revision_hash", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("artifact_ref", sa.Text(), nullable=False),
        sa.Column("generator_revision", sa.String(length=64), nullable=False),
        sa.Column("evidence_refs", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(
            ["topology_snapshot_id"],
            ["workspace_group_topology_snapshots.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "projection_type",
            "scope_type",
            "scope_id",
            "input_revision_hash",
            name="uq_knowledge_projection_revision",
        ),
    )
    op.create_index(
        "idx_knowledge_projection_scope_generated",
        "knowledge_projection_manifests",
        ["scope_type", "scope_id", "generated_at"],
    )

    op.create_table(
        "group_synthesis_receipts",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("group_id", sa.String(length=64), nullable=False),
        sa.Column("topology_snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("policy_revision", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="candidate"),
        sa.Column("candidate_memory_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("conflict_sets", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("review_projection_id", sa.String(length=64), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(
            ["topology_snapshot_id"],
            ["workspace_group_topology_snapshots.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["review_projection_id"],
            ["knowledge_projection_manifests.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("run_id", "input_hash", name="uq_group_synthesis_run_input"),
        sa.CheckConstraint(
            "status IN ('candidate', 'approved', 'changes_requested', 'rejected')",
            name="chk_group_synthesis_receipt_status",
        ),
    )
    op.create_index(
        "idx_group_synthesis_receipts_group_created",
        "group_synthesis_receipts",
        ["group_id", "created_at"],
    )

    op.create_table(
        "group_synthesis_review_receipts",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("synthesis_receipt_id", sa.String(length=64), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("actor_user_id", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("decision_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(
            ["synthesis_receipt_id"],
            ["group_synthesis_receipts.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "synthesis_receipt_id",
            "decision_hash",
            name="uq_group_synthesis_review_decision",
        ),
        sa.CheckConstraint(
            "decision IN ('approve', 'request_changes', 'reject')",
            name="chk_group_synthesis_review_decision",
        ),
    )


def downgrade() -> None:
    op.drop_table("group_synthesis_review_receipts")
    op.drop_index(
        "idx_group_synthesis_receipts_group_created",
        table_name="group_synthesis_receipts",
    )
    op.drop_table("group_synthesis_receipts")
    op.drop_index(
        "idx_knowledge_projection_scope_generated",
        table_name="knowledge_projection_manifests",
    )
    op.drop_table("knowledge_projection_manifests")
    op.drop_index(
        "idx_knowledge_source_intakes_source_created",
        table_name="knowledge_source_intakes",
    )
    op.drop_table("knowledge_source_intakes")
    op.drop_index(
        "idx_knowledge_source_states_owner",
        table_name="knowledge_source_states",
    )
    op.drop_table("knowledge_source_states")
