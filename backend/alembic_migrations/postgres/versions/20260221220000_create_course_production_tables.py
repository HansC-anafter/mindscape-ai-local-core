"""create course production tables

Revision ID: 20260221220000
Revises:
Create Date: 2026-02-21 22:00:00

Creates the course_production capability tables:
- voice_profiles
- voice_training_jobs
- video_segments

Idempotent: uses Inspector to skip tables/indexes that already exist.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import ProgrammingError

# revision identifiers, used by Alembic
revision: str = "20260221220000"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _index_exists(inspector, table_name: str, index_name: str) -> bool:
    if not _table_exists(inspector, table_name):
        return False
    return any(idx["name"] == index_name for idx in inspector.get_indexes(table_name))


def upgrade() -> None:
    """Create course production tables (idempotent)."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # ----------------------------------------------------------------
    # voice_profiles
    # ----------------------------------------------------------------
    if not _table_exists(inspector, "voice_profiles"):
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

    conn = op.get_bind()
    def attempt_index(stmt):
        try:
            with conn.begin_nested():
                conn.execute(sa.text(stmt))
        except ProgrammingError:
            pass
            
    attempt_index("CREATE INDEX idx_voice_profiles_workspace ON voice_profiles (workspace_id)")
    attempt_index("CREATE INDEX idx_voice_profiles_instructor ON voice_profiles (instructor_id)")
    attempt_index("CREATE INDEX idx_voice_profiles_status ON voice_profiles (status)")
    attempt_index("CREATE INDEX idx_voice_profiles_ws_instructor ON voice_profiles (workspace_id, instructor_id)")
    attempt_index("CREATE INDEX idx_voice_profiles_sample_paths ON voice_profiles USING gin (sample_paths)")

    # ----------------------------------------------------------------
    # voice_training_jobs
    # ----------------------------------------------------------------
    if not _table_exists(inspector, "voice_training_jobs"):
        op.create_table(
            "voice_training_jobs",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("workspace_id", sa.Text, nullable=False),
            sa.Column(
                "voice_profile_id", postgresql.UUID(as_uuid=True), nullable=False
            ),
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

    attempt_index("CREATE INDEX idx_voice_training_jobs_workspace ON voice_training_jobs (workspace_id)")
    attempt_index("CREATE INDEX idx_voice_training_jobs_profile ON voice_training_jobs (voice_profile_id)")
    attempt_index("CREATE INDEX idx_voice_training_jobs_instructor ON voice_training_jobs (instructor_id)")
    attempt_index("CREATE INDEX idx_voice_training_jobs_status ON voice_training_jobs (status)")
    attempt_index("CREATE INDEX idx_voice_training_jobs_config ON voice_training_jobs USING gin (training_config)")

    # ----------------------------------------------------------------
    # video_segments
    # ----------------------------------------------------------------
    if not _table_exists(inspector, "video_segments"):
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

    attempt_index("CREATE INDEX idx_video_segments_workspace ON video_segments (workspace_id)")
    attempt_index("CREATE INDEX idx_video_segments_instructor ON video_segments (instructor_id)")
    attempt_index("CREATE INDEX idx_video_segments_course ON video_segments (course_id)")
    attempt_index("CREATE INDEX idx_video_segments_quality ON video_segments (quality_score DESC)")
    attempt_index("CREATE INDEX idx_video_segments_tags ON video_segments USING gin (tags)")
    attempt_index("CREATE INDEX idx_video_segments_ws_source ON video_segments (workspace_id, source_video_path)")


def downgrade() -> None:
    """Drop course production tables."""
    op.drop_table("video_segments")
    op.drop_table("voice_training_jobs")
    op.drop_table("voice_profiles")
