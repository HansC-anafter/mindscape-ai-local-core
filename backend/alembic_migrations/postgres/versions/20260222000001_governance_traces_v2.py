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
from sqlalchemy.exc import ProgrammingError

# revision identifiers
revision = "20260222000001"
down_revision = "20260222000000"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    
    # helper for clean try/except in pg transactions
    def attempt(stmt):
        try:
            with conn.begin_nested():
                conn.execute(sa.text(stmt))
        except ProgrammingError:
            pass
            
    attempt("ALTER TABLE reasoning_traces ADD COLUMN parent_trace_id TEXT")
    attempt("ALTER TABLE reasoning_traces ADD COLUMN supersedes TEXT")
    attempt("ALTER TABLE reasoning_traces ADD COLUMN meeting_session_id TEXT")
    attempt("CREATE INDEX idx_reasoning_traces_parent ON reasoning_traces (parent_trace_id)")
    attempt("CREATE INDEX idx_reasoning_traces_session ON reasoning_traces (meeting_session_id)")


def downgrade():
    op.drop_index("idx_reasoning_traces_session")
    op.drop_index("idx_reasoning_traces_parent")
    op.drop_column("reasoning_traces", "meeting_session_id")
    op.drop_column("reasoning_traces", "supersedes")
    op.drop_column("reasoning_traces", "parent_trace_id")
