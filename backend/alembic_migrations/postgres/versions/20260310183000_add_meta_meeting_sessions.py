"""Add meta_meeting_sessions table.

ADR-001 v2 Phase 3: Meta Meeting State Machine.

Revision ID: 20260310183000
Revises: 20260310170000
Create Date: 2026-03-10T18:30:00
"""
from alembic import op
import sqlalchemy as sa

revision = "20260310183000"
down_revision = "20260310170000"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "meta_meeting_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_profile_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("meta_scope_id", sa.String(36), nullable=True),
        sa.Column("scope_snapshot", sa.Text, server_default="{}"),
        sa.Column("digest_ids", sa.Text, server_default="[]"),
        sa.Column("digest_count", sa.Integer, server_default="0"),
        sa.Column("digest_time_window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("digest_time_window_end", sa.DateTime(timezone=True), nullable=True),
        # Meeting content
        sa.Column("agenda", sa.Text, server_default="[]"),
        sa.Column("success_criteria", sa.Text, server_default="[]"),
        sa.Column("minutes_md", sa.Text, server_default=""),
        sa.Column("action_items", sa.Text, server_default="[]"),
        sa.Column("decisions", sa.Text, server_default="[]"),
        sa.Column("round_count", sa.Integer, server_default="0"),
        sa.Column("max_rounds", sa.Integer, server_default="5"),
        # Writeback tracking
        sa.Column("writeback_receipts", sa.Text, server_default="[]"),
        sa.Column("writeback_summary", sa.Text, server_default="{}"),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("prepared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        # Metadata
        sa.Column("metadata", sa.Text, server_default="{}"),
    )

    op.create_index(
        "ix_meta_meeting_sessions_owner",
        "meta_meeting_sessions",
        ["owner_profile_id", "status"],
    )
    op.create_index(
        "ix_meta_meeting_sessions_created",
        "meta_meeting_sessions",
        ["created_at"],
    )


def downgrade():
    op.drop_index("ix_meta_meeting_sessions_created")
    op.drop_index("ix_meta_meeting_sessions_owner")
    op.drop_table("meta_meeting_sessions")
