"""init_mindscape_tables

Revision ID: 20251227174800
Revises:
Create Date: 2025-12-27 17:48:00

Initializes core mindscape tables migrated from init_db.py.
This migration replaces the DDL in init_db.py.

Tables created:
- mindscape_personal
- mindscape_suggestions
- playbook_knowledge
- external_docs
- voice_profiles
- voice_training_jobs
- video_segments
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20251227174800"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all mindscape tables from init_db.py"""

    # Ensure pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # mindscape_personal table
    # Note: vector type needs to be created via raw SQL
    op.execute(
        """
        CREATE TABLE mindscape_personal (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id TEXT NOT NULL DEFAULT 'default_user',
            source_type TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata JSONB,
            source_id TEXT,
            source_context TEXT,
            confidence REAL DEFAULT 0.5,
            weight REAL DEFAULT 1.0,
            embedding vector(1536),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """
    )

    # Indexes for mindscape_personal
    op.create_index("idx_mindscape_personal_user", "mindscape_personal", ["user_id"])
    op.create_index(
        "idx_mindscape_personal_source", "mindscape_personal", ["source_type"]
    )
    op.create_index(
        "idx_mindscape_personal_updated_at",
        "mindscape_personal",
        [sa.text("updated_at DESC")],
    )
    op.create_index(
        "idx_mindscape_personal_metadata",
        "mindscape_personal",
        ["metadata"],
        postgresql_using="gin",
    )

    # mindscape_suggestions table
    op.create_table(
        "mindscape_suggestions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", sa.Text, nullable=False, server_default="default_user"),
        sa.Column("suggestion_type", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("suggested_data", postgresql.JSONB),
        sa.Column("source_seed_ids", postgresql.ARRAY(postgresql.UUID)),
        sa.Column("source_summary", sa.Text),
        sa.Column("confidence", sa.REAL, nullable=False),
        sa.Column("status", sa.Text, server_default="pending"),
        sa.Column("reviewed_at", sa.DateTime),
        sa.Column("reviewed_by", sa.Text),
        sa.Column("generated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    # Indexes for mindscape_suggestions
    op.create_index("idx_suggestions_user", "mindscape_suggestions", ["user_id"])
    op.create_index("idx_suggestions_status", "mindscape_suggestions", ["status"])
    op.create_index(
        "idx_suggestions_generated_at",
        "mindscape_suggestions",
        [sa.text("generated_at DESC")],
    )

    # playbook_knowledge table
    op.execute(
        """
        CREATE TABLE playbook_knowledge (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            playbook_code TEXT NOT NULL,
            section_type TEXT NOT NULL,
            content TEXT NOT NULL,
            embedding vector(1536),
            metadata JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """
    )

    # Indexes for playbook_knowledge
    op.create_index(
        "idx_playbook_knowledge_code", "playbook_knowledge", ["playbook_code"]
    )
    op.create_index(
        "idx_playbook_knowledge_section", "playbook_knowledge", ["section_type"]
    )
    op.create_index(
        "idx_playbook_knowledge_metadata",
        "playbook_knowledge",
        ["metadata"],
        postgresql_using="gin",
    )

    # external_docs table
    op.execute(
        """
        CREATE TABLE external_docs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id TEXT NOT NULL DEFAULT 'default_user',
            source_app TEXT NOT NULL,
            source_id TEXT NOT NULL,
            doc_type TEXT,
            title TEXT,
            content TEXT NOT NULL,
            embedding vector(1536),
            metadata JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            last_synced_at TIMESTAMP
        )
    """
    )

    # Indexes for external_docs
    op.create_index("idx_external_docs_user", "external_docs", ["user_id"])
    op.create_index("idx_external_docs_source", "external_docs", ["source_app"])
    op.create_index(
        "idx_external_docs_source_id", "external_docs", ["source_app", "source_id"]
    )
    op.create_index(
        "idx_external_docs_metadata",
        "external_docs",
        ["metadata"],
        postgresql_using="gin",
    )
    op.create_index(
        "idx_external_docs_unique_source",
        "external_docs",
        ["user_id", "source_app", "source_id"],
        unique=True,
    )

    # voice_profiles table
    op.create_table(
        "voice_profiles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("instructor_id", sa.Text, nullable=False),
        sa.Column("version", sa.Integer, server_default="1"),
        sa.Column("profile_name", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("sample_duration_seconds", sa.REAL),
        sa.Column("sample_count", sa.Integer, server_default="0"),
        sa.Column("sample_paths", postgresql.JSONB),
        sa.Column("model_storage_path", sa.Text),
        sa.Column("model_storage_service", sa.Text),
        sa.Column("training_job_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("ready_at", sa.DateTime),
        sa.Column("quality_score", sa.REAL),
        sa.Column("similarity_score", sa.REAL),
    )

    # Indexes for voice_profiles
    op.create_index(
        "idx_voice_profiles_instructor", "voice_profiles", ["instructor_id"]
    )
    op.create_index("idx_voice_profiles_status", "voice_profiles", ["status"])
    op.create_index(
        "idx_voice_profiles_sample_paths",
        "voice_profiles",
        ["sample_paths"],
        postgresql_using="gin",
    )

    # voice_training_jobs table
    op.create_table(
        "voice_training_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("voice_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("instructor_id", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="queued"),
        sa.Column("priority", sa.Text, nullable=False, server_default="normal"),
        sa.Column("training_config", postgresql.JSONB),
        sa.Column("sample_file_paths", postgresql.JSONB),
        sa.Column("sample_metadata", postgresql.JSONB),
        sa.Column("started_at", sa.DateTime),
        sa.Column("completed_at", sa.DateTime),
        sa.Column("estimated_duration_seconds", sa.Integer),
        sa.Column("actual_duration_seconds", sa.Integer),
        sa.Column("result_model_path", sa.Text),
        sa.Column("result_metrics", postgresql.JSONB),
        sa.Column("error_message", sa.Text),
        sa.Column("error_stack", sa.Text),
        sa.Column("gpu_used", sa.Text),
        sa.Column("compute_cost", sa.REAL),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("log_path", sa.Text),
        sa.ForeignKeyConstraint(["voice_profile_id"], ["voice_profiles.id"]),
    )

    # Indexes for voice_training_jobs
    op.create_index(
        "idx_voice_training_jobs_profile", "voice_training_jobs", ["voice_profile_id"]
    )
    op.create_index(
        "idx_voice_training_jobs_instructor", "voice_training_jobs", ["instructor_id"]
    )
    op.create_index("idx_voice_training_jobs_status", "voice_training_jobs", ["status"])
    op.create_index(
        "idx_voice_training_jobs_config",
        "voice_training_jobs",
        ["training_config"],
        postgresql_using="gin",
    )

    # video_segments table
    op.create_table(
        "video_segments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
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
        sa.Column("last_used_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("analysis_job_id", postgresql.UUID(as_uuid=True)),
    )

    # Indexes for video_segments
    op.create_index(
        "idx_video_segments_instructor", "video_segments", ["instructor_id"]
    )
    op.create_index("idx_video_segments_course", "video_segments", ["course_id"])
    op.create_index(
        "idx_video_segments_quality", "video_segments", [sa.text("quality_score DESC")]
    )
    op.create_index(
        "idx_video_segments_tags", "video_segments", ["tags"], postgresql_using="gin"
    )


def downgrade() -> None:
    """Drop all mindscape tables"""
    op.drop_table("video_segments")
    op.drop_table("voice_training_jobs")
    op.drop_table("voice_profiles")
    op.drop_table("external_docs")
    op.drop_table("playbook_knowledge")
    op.drop_table("mindscape_suggestions")
    op.drop_table("mindscape_personal")
    op.execute("DROP EXTENSION IF EXISTS vector")
