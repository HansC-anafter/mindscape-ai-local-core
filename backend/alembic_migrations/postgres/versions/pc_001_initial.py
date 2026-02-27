"""
Practice Companion - Initial Migration

Revision: pc_001_initial
Creates: pc_teacher_profiles, pc_sessions, pc_progress
"""

from alembic import op
import sqlalchemy as sa

revision = "pc_001_initial"
down_revision = None
branch_labels = ("practice_companion",)
depends_on = None


def upgrade():
    op.create_table(
        "pc_teacher_profiles",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("workspace_id", sa.String(64), nullable=False, index=True),
        sa.Column("teacher_id", sa.String(64), nullable=False, index=True),
        sa.Column("profile_code", sa.String(64), nullable=False),
        sa.Column(
            "profile_version", sa.String(16), nullable=False, server_default="latest"
        ),
        sa.Column("config_overrides", sa.JSON, nullable=True),
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
        sa.UniqueConstraint("workspace_id", "teacher_id", name="uq_pc_teacher_profile"),
    )

    op.create_table(
        "pc_sessions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("workspace_id", sa.String(64), nullable=False, index=True),
        sa.Column("user_id", sa.String(64), nullable=False, index=True),
        sa.Column("teacher_id", sa.String(64), nullable=True),
        sa.Column("profile_code", sa.String(64), nullable=False),
        sa.Column("practice_type_code", sa.String(64), nullable=False),
        sa.Column("entry_text", sa.Text, nullable=True),
        sa.Column("duration_min", sa.Integer, nullable=True),
        sa.Column("dimension_self_scores", sa.JSON, nullable=True),
        sa.Column("dimension_ai_scores", sa.JSON, nullable=True),
        sa.Column("analysis_result", sa.JSON, nullable=True),
        sa.Column("feedback_text", sa.Text, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="logged"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "pc_progress",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("workspace_id", sa.String(64), nullable=False, index=True),
        sa.Column("user_id", sa.String(64), nullable=False, index=True),
        sa.Column("profile_code", sa.String(64), nullable=False),
        sa.Column("dimension_code", sa.String(64), nullable=False),
        sa.Column("total_sessions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("current_streak", sa.Integer, nullable=False, server_default="0"),
        sa.Column("best_streak", sa.Integer, nullable=False, server_default="0"),
        sa.Column("latest_score", sa.Float, nullable=True),
        sa.Column("avg_score_7d", sa.Float, nullable=True),
        sa.Column("avg_score_30d", sa.Float, nullable=True),
        sa.Column("trend_direction", sa.String(16), nullable=True),
        sa.Column("last_practice_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "user_id",
            "profile_code",
            "dimension_code",
            name="uq_pc_progress_dimension",
        ),
    )


def downgrade():
    op.drop_table("pc_progress")
    op.drop_table("pc_sessions")
    op.drop_table("pc_teacher_profiles")
