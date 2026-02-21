"""Add meeting_sessions table

Revision ID: 20260222000003
Revises: 20260222000002
Create Date: 2026-02-22 04:50:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "20260222000003"
down_revision = "20260222000002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "meeting_sessions",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("workspace_id", sa.Text(), nullable=False),
        sa.Column("thread_id", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "state_before",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "state_after",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "decisions",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "traces",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "intents_patched",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    # Index for list_by_workspace and per-thread lookup
    op.create_index(
        "idx_meeting_sessions_ws_thread",
        "meeting_sessions",
        ["workspace_id", "thread_id"],
    )

    # Index for get_active_session (WHERE ended_at IS NULL)
    op.create_index(
        "idx_meeting_sessions_active",
        "meeting_sessions",
        ["workspace_id", "ended_at"],
    )


def downgrade():
    op.drop_index("idx_meeting_sessions_active", table_name="meeting_sessions")
    op.drop_index("idx_meeting_sessions_ws_thread", table_name="meeting_sessions")
    op.drop_table("meeting_sessions")
