"""Add L2 Bridge tables: goal_sets, goal_clauses, meeting_extracts, meeting_extract_items, lens_patches

Revision ID: 20260224000000
Revises: 20260223000003
Create Date: 2026-02-24

Creates tables for the L2 Bridge architecture:
- goal_sets: Project goal target sets (GoalSet model)
- goal_clauses: Individual goal clauses with GoalCategory enum
- meeting_extracts: Typed X_t outputs from meeting sessions (MeetingExtract model)
- meeting_extract_items: Individual extract items with ExtractType enum
- lens_patches: Versioned lens delta records for Drift computation (LensPatch model)
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260224000000"
down_revision: Union[str, Sequence[str]] = "20260223000003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- goal_sets (matches GoalSet model) ---
    op.create_table(
        "goal_sets",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("workspace_id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=True,
            server_default="{}",
        ),
    )
    op.create_index(
        "idx_goal_sets_ws_project", "goal_sets", ["workspace_id", "project_id"]
    )

    # --- goal_clauses (matches GoalClause model: category, not clause_type) ---
    op.create_table(
        "goal_clauses",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column(
            "goal_set_id",
            sa.Text(),
            sa.ForeignKey("goal_sets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.Text(), nullable=False),  # GoalCategory enum
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column(
            "evidence_required",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column("embedding", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=True,
            server_default="{}",
        ),
    )
    op.create_index("idx_goal_clauses_set", "goal_clauses", ["goal_set_id"])

    # --- meeting_extracts (matches MeetingExtract model) ---
    op.create_table(
        "meeting_extracts",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("meeting_session_id", sa.Text(), nullable=False),
        sa.Column(
            "state_snapshot",
            postgresql.JSONB(),
            nullable=True,
            server_default="{}",
        ),
        sa.Column("goal_set_id", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=True,
            server_default="{}",
        ),
    )
    op.create_index(
        "idx_meeting_extracts_session",
        "meeting_extracts",
        ["meeting_session_id"],
    )

    # --- meeting_extract_items (matches MeetingExtractItem model) ---
    op.create_table(
        "meeting_extract_items",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("meeting_session_id", sa.Text(), nullable=False),
        sa.Column(
            "extract_id",
            sa.Text(),
            sa.ForeignKey("meeting_extracts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("extract_type", sa.Text(), nullable=False),  # ExtractType enum
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", postgresql.JSONB(), nullable=True),
        sa.Column(
            "source_event_ids",
            postgresql.JSONB(),
            nullable=True,
            server_default="[]",
        ),
        sa.Column(
            "evidence_refs",
            postgresql.JSONB(),
            nullable=True,
            server_default="[]",
        ),
        sa.Column(
            "goal_clause_ids",
            postgresql.JSONB(),
            nullable=True,
            server_default="[]",
        ),
        sa.Column("confidence", sa.Float(), nullable=True, server_default="0.0"),
        sa.Column("agent_id", sa.Text(), nullable=True),
        sa.Column("round_number", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=True,
            server_default="{}",
        ),
    )
    op.create_index(
        "idx_meeting_extract_items_extract",
        "meeting_extract_items",
        ["extract_id"],
    )

    # --- lens_patches (matches LensPatch model) ---
    op.create_table(
        "lens_patches",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("lens_id", sa.Text(), nullable=False),
        sa.Column("meeting_session_id", sa.Text(), nullable=False),
        sa.Column(
            "delta",
            postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "evidence_refs",
            postgresql.JSONB(),
            nullable=True,
            server_default="[]",
        ),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("status", sa.Text(), nullable=False, server_default="proposed"),
        sa.Column("rollback_to", sa.Text(), nullable=True),
        sa.Column(
            "lens_version_before",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("lens_version_after", sa.Integer(), nullable=True),
        sa.Column("approved_by", sa.Text(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=True,
            server_default="{}",
        ),
    )
    op.create_index("idx_lens_patches_lens", "lens_patches", ["lens_id"])
    op.create_index("idx_lens_patches_session", "lens_patches", ["meeting_session_id"])
    op.create_index(
        "idx_lens_patches_chain", "lens_patches", ["lens_id", "lens_version_before"]
    )


def downgrade() -> None:
    op.drop_table("meeting_extract_items")
    op.drop_table("meeting_extracts")
    op.drop_table("goal_clauses")
    op.drop_table("goal_sets")
    op.drop_table("lens_patches")
