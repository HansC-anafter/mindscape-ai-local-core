"""Add governance columns to reasoning_traces (parent_trace_id, supersedes, meeting_session_id).

Revision ID: 20260222000001
Revises: 20260222000000
Create Date: 2026-02-22 00:00:01.000000

Adds versioning and session linkage columns for the intent governance paradigm:
- parent_trace_id: links to previous version of a trace (Axiom 3: patchable)
- supersedes: JSON array of trace IDs this trace replaces
- meeting_session_id: links trace to a governance meeting session (Axiom 4: replayable)
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "20260222000001"
down_revision = "20260222000000"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "reasoning_traces",
        sa.Column("parent_trace_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "reasoning_traces",
        sa.Column("supersedes", sa.Text(), nullable=True),
    )
    op.add_column(
        "reasoning_traces",
        sa.Column("meeting_session_id", sa.Text(), nullable=True),
    )
    op.create_index(
        "idx_reasoning_traces_parent",
        "reasoning_traces",
        ["parent_trace_id"],
    )
    op.create_index(
        "idx_reasoning_traces_session",
        "reasoning_traces",
        ["meeting_session_id"],
    )


def downgrade():
    op.drop_index("idx_reasoning_traces_session")
    op.drop_index("idx_reasoning_traces_parent")
    op.drop_column("reasoning_traces", "meeting_session_id")
    op.drop_column("reasoning_traces", "supersedes")
    op.drop_column("reasoning_traces", "parent_trace_id")
