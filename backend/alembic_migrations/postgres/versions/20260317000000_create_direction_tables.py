"""
Migration: Create direction_sessions and direction_artifacts tables.

Revision ID: 20260317000000
Create Date: 2026-03-17
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

# revision identifiers, used by Alembic.
revision = "20260317000000"
down_revision = None
branch_labels = ("performance_direction",)
depends_on = None


def upgrade() -> None:
    op.create_table(
        "direction_sessions",
        sa.Column("session_id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(64), nullable=False, index=True),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "active",
                "completed",
                "archived",
                name="direction_session_status",
            ),
            server_default="draft",
            nullable=False,
        ),
        sa.Column("intent", JSONB, nullable=True),
        sa.Column("cast", JSONB, nullable=True),
        sa.Column("reference_ids", ARRAY(sa.String), server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "direction_artifacts",
        sa.Column("artifact_id", sa.String(64), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(64),
            sa.ForeignKey("direction_sessions.session_id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "artifact_type",
            sa.Enum(
                "performer_cue",
                "shot_card",
                "body_map",
                "recipe_note",
                "compiled_ref",
                name="direction_artifact_type",
            ),
            nullable=False,
        ),
        sa.Column("content_json", JSONB, nullable=True),
        sa.Column("asset_path", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("direction_artifacts")
    op.drop_table("direction_sessions")
    op.execute("DROP TYPE IF EXISTS direction_artifact_type")
    op.execute("DROP TYPE IF EXISTS direction_session_status")
