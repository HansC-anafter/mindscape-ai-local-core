"""create course production tables

Revision ID: 20260221220000
Revises:
Create Date: 2026-02-21 22:00:00

Creates the course_production capability tables:
- voice_profiles
- voice_training_jobs
- video_segments

This migration mirrors the table definitions from local-core's
20251227174800_init_mindscape_tables.py with the following enhancements:
- workspace_id added to all tables for multi-tenant isolation
- Timestamps use TIMESTAMP WITH TIME ZONE (timezone-aware)
- Indexes include workspace_id for partition-friendly queries
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision: str = "20260221220000"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create course production tables."""

    # ----------------------------------------------------------------
    # voice_profiles
    # ----------------------------------------------------------------
    op.create_table(
        "voice_profiles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", sa.Text, nullable=False),
        sa.Column("instructor_id", sa.Text, nullable=False),
        sa.Column("version", sa.Integer, server_default="1"),
        sa.Column("profile_name", sa.Text, nullable=False),
        sa.Column("language", sa.Text, server_default="zh-TW"),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("sample_duration_seconds", sa.REAL),
        sa.Column("sample_count", sa.Integer, server_default="0"),
        sa.Column("sample_paths", postgresql.JSONB),
        sa.Column("model_storage_path", sa.Text),
        sa.Column("model_storage_service", sa.Text),
        sa.Column("training_job_id", postgresql.UUID(as_uuid=True)),
        sa.Column("quality_score", sa.REAL),
        sa.Column("similarity_score", sa.REAL),
        sa.Column("training_config", postgresql.JSONB),
        sa.Column("metadata", postgresql.JSONB),
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
        sa.Column("ready_at", sa.DateTime(timezone=True)),
    )

    op.create_index("idx_voice_profiles_workspace", "voice_profiles", ["workspace_id"])
    op.create_index(
        "idx_voice_profiles_instructor", "voice_profiles", ["instructor_id"]
    )
    op.create_index("idx_voice_profiles_status", "voice_profiles", ["status"])
    op.create_index(
        "idx_voice_profiles_ws_instructor",
        "voice_profiles",
        ["workspace_id", "instructor_id"],
    )
    op.create_index(
        "idx_voice_profiles_sample_paths",
        "voice_profiles",
        ["sample_paths"],
        postgresql_using="gin",
    )

    # ----------------------------------------------------------------
    # voice_training_jobs
    # ----------------------------------------------------------------
    op.create_table(
        "voice_training_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", sa.Text, nullable=False),
        sa.Column("voice_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("instructor_id", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="queued"),
        sa.Column("priority", sa.Text, nullable=False, server_default="normal"),
        sa.Column("training_config", postgresql.JSONB),
        sa.Column("sample_file_paths", postgresql.JSONB),
        sa.Column("sample_metadata", postgresql.JSONB),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("estimated_duration_seconds", sa.Integer),
        sa.Column("actual_duration_seconds", sa.Integer),
        sa.Column("result_model_path", sa.Text),
        sa.Column("result_metrics", postgresql.JSONB),
        sa.Column("error_message", sa.Text),
        sa.Column("error_stack", sa.Text),
        sa.Column("gpu_used", sa.Text),
        sa.Column("compute_cost", sa.REAL),
        sa.Column("log_path", sa.Text),
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
        sa.ForeignKeyConstraint(["voice_profile_id"], ["voice_profiles.id"]),
    )

    op.create_index(
        "idx_voice_training_jobs_workspace",
        "voice_training_jobs",
        ["workspace_id"],
    )
    op.create_index(
        "idx_voice_training_jobs_profile",
        "voice_training_jobs",
        ["voice_profile_id"],
    )
    op.create_index(
        "idx_voice_training_jobs_instructor",
        "voice_training_jobs",
        ["instructor_id"],
    )
    op.create_index(
        "idx_voice_training_jobs_status",
        "voice_training_jobs",
        ["status"],
    )
    op.create_index(
        "idx_voice_training_jobs_config",
        "voice_training_jobs",
        ["training_config"],
        postgresql_using="gin",
    )

    # ----------------------------------------------------------------
    # video_segments
    # ----------------------------------------------------------------
    op.create_table(
        "video_segments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", sa.Text, nullable=False),
        sa.Column("instructor_id", sa.Text, nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True)),
        sa.Column("source_video_path", sa.Text, nullable=False),
        sa.Column("source_video_id", sa.Text, nullable=False),
        sa.Column("start_time", sa.REAL, nullable=False),
        sa.Column("end_time", sa.REAL, nullable=False),
        sa.Column("duration", sa.REAL, nullable=False),
        sa.Column("segment_file_path", sa.Text),
        sa.Column("shot_type", sa.Text),
        sa.Column("quality_score", sa.REAL, server_default="0.0"),
        sa.Column("quality_level", sa.Text, server_default="fair"),
        sa.Column("tags", postgresql.JSONB),
        sa.Column("action_names", postgresql.JSONB),
        sa.Column("intent_tags", postgresql.JSONB),
        sa.Column("script_line_ids", postgresql.JSONB),
        sa.Column("script_alignment_confidence", sa.REAL),
        sa.Column("pose_estimation", postgresql.JSONB),
        sa.Column("composition_features", postgresql.JSONB),
        sa.Column("lighting_quality", sa.REAL),
        sa.Column("framing_quality", sa.REAL),
        sa.Column("transcript", sa.Text),
        sa.Column("transcript_confidence", sa.REAL),
        sa.Column("usage_count", sa.Integer, server_default="0"),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("analysis_job_id", postgresql.UUID(as_uuid=True)),
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

    op.create_index("idx_video_segments_workspace", "video_segments", ["workspace_id"])
    op.create_index(
        "idx_video_segments_instructor", "video_segments", ["instructor_id"]
    )
    op.create_index("idx_video_segments_course", "video_segments", ["course_id"])
    op.create_index(
        "idx_video_segments_quality",
        "video_segments",
        [sa.text("quality_score DESC")],
    )
    op.create_index(
        "idx_video_segments_tags",
        "video_segments",
        ["tags"],
        postgresql_using="gin",
    )
    op.create_index(
        "idx_video_segments_ws_source",
        "video_segments",
        ["workspace_id", "source_video_path"],
    )


def downgrade() -> None:
    """Drop course production tables."""
    op.drop_table("video_segments")
    op.drop_table("voice_training_jobs")
    op.drop_table("voice_profiles")
