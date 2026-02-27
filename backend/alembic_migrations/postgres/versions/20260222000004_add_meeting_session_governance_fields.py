"""Add governance fields to meeting_sessions and meeting-session event index.

Revision ID: 20260222000004
Revises: 20260222000003
Create Date: 2026-02-22 07:20:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260222000004"
down_revision = "20260222000003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "meeting_sessions",
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default="planned",
        ),
    )
    op.add_column(
        "meeting_sessions",
        sa.Column(
            "meeting_type",
            sa.Text(),
            nullable=False,
            server_default="general",
        ),
    )
    op.add_column(
        "meeting_sessions",
        sa.Column(
            "agenda",
            postgresql.JSONB(),
            nullable=True,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "meeting_sessions",
        sa.Column(
            "success_criteria",
            postgresql.JSONB(),
            nullable=True,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "meeting_sessions",
        sa.Column(
            "round_count",
            sa.Integer(),
            nullable=True,
            server_default="0",
        ),
    )
    op.add_column(
        "meeting_sessions",
        sa.Column(
            "max_rounds",
            sa.Integer(),
            nullable=True,
            server_default="5",
        ),
    )
    op.add_column(
        "meeting_sessions",
        sa.Column(
            "action_items",
            postgresql.JSONB(),
            nullable=True,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "meeting_sessions",
        sa.Column(
            "minutes_md",
            sa.Text(),
            nullable=True,
            server_default="",
        ),
    )

    # Fast lookup for timeline replay by meeting_session_id in metadata JSONB.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mind_events_meeting_session
        ON mind_events (((metadata::jsonb)->>'meeting_session_id'))
        WHERE (metadata::jsonb)->>'meeting_session_id' IS NOT NULL
        """
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_mind_events_meeting_session")
    op.drop_column("meeting_sessions", "minutes_md")
    op.drop_column("meeting_sessions", "action_items")
    op.drop_column("meeting_sessions", "max_rounds")
    op.drop_column("meeting_sessions", "round_count")
    op.drop_column("meeting_sessions", "success_criteria")
    op.drop_column("meeting_sessions", "agenda")
    op.drop_column("meeting_sessions", "meeting_type")
    op.drop_column("meeting_sessions", "status")
