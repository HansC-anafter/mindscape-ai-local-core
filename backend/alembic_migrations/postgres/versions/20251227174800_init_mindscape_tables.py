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


def _get_column_udt_name(table_name: str, column_name: str) -> str | None:
    """Return the PostgreSQL UDT name for a column, if it exists."""
    bind = op.get_bind()
    result = bind.execute(
        sa.text(
            """
            SELECT udt_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = :table_name
              AND column_name = :column_name
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    )
    return result.scalar()


def _upgrade_existing_mindscape_personal_table() -> None:
    """Repair the legacy mindscape_personal schema before creating new indexes."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("mindscape_personal"):
        return

    existing_columns = {
        column["name"]
        for column in inspector.get_columns("mindscape_personal")
    }

    if "content" not in existing_columns:
        op.add_column("mindscape_personal", sa.Column("content", sa.Text(), nullable=True))
        existing_columns.add("content")

    if "source_context" not in existing_columns:
        op.add_column(
            "mindscape_personal",
            sa.Column("source_context", sa.Text(), nullable=True),
        )
        existing_columns.add("source_context")

    if "content" in existing_columns:
        if "seed_text" in existing_columns:
            op.execute(
                """
                UPDATE mindscape_personal
                SET content = COALESCE(NULLIF(content, ''), seed_text, '')
                WHERE content IS NULL OR content = ''
                """
            )
        else:
            op.execute(
                """
                UPDATE mindscape_personal
                SET content = ''
                WHERE content IS NULL
                """
            )
        op.execute(
            """
            ALTER TABLE mindscape_personal
            ALTER COLUMN content SET DEFAULT ''
            """
        )
        op.execute(
            """
            ALTER TABLE mindscape_personal
            ALTER COLUMN content SET NOT NULL
            """
        )

    metadata_udt_name = _get_column_udt_name("mindscape_personal", "metadata")
    if metadata_udt_name and metadata_udt_name != "jsonb":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION _mindscape_try_parse_jsonb(value TEXT)
            RETURNS JSONB
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF value IS NULL OR btrim(value) = '' THEN
                    RETURN NULL;
                END IF;
                BEGIN
                    RETURN value::jsonb;
                EXCEPTION WHEN others THEN
                    RETURN to_jsonb(value);
                END;
            END;
            $$;
            """
        )
        op.execute(
            """
            ALTER TABLE mindscape_personal
            ALTER COLUMN metadata TYPE JSONB
            USING _mindscape_try_parse_jsonb(metadata)
            """
        )
        op.execute("DROP FUNCTION IF EXISTS _mindscape_try_parse_jsonb(TEXT)")


def _upgrade_existing_external_docs_table() -> None:
    """Repair the legacy external_docs schema before creating new indexes."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("external_docs"):
        return

    existing_columns = {
        column["name"]
        for column in inspector.get_columns("external_docs")
    }

    if "source_id" not in existing_columns:
        op.add_column("external_docs", sa.Column("source_id", sa.Text(), nullable=True))
        existing_columns.add("source_id")

    if "doc_type" not in existing_columns:
        op.add_column("external_docs", sa.Column("doc_type", sa.Text(), nullable=True))
        existing_columns.add("doc_type")

    if "last_synced_at" not in existing_columns:
        op.add_column(
            "external_docs",
            sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        )
        existing_columns.add("last_synced_at")

    if "source_id" in existing_columns:
        op.execute(
            """
            UPDATE external_docs
            SET source_id = COALESCE(
                NULLIF(source_id, ''),
                NULLIF(title, ''),
                source_app || ':' || id::text
            )
            WHERE source_id IS NULL OR source_id = ''
            """
        )
        op.execute(
            """
            ALTER TABLE external_docs
            ALTER COLUMN source_id SET NOT NULL
            """
        )


def upgrade() -> None:
    """Create all mindscape tables from init_db.py"""
    inspector = sa.inspect(op.get_bind())

    # Ensure pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # mindscape_personal table
    # Note: vector type needs to be created via raw SQL
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mindscape_personal (
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

    _upgrade_existing_mindscape_personal_table()

    # Indexes for mindscape_personal
    op.execute("CREATE INDEX IF NOT EXISTS idx_mindscape_personal_user ON mindscape_personal (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mindscape_personal_source ON mindscape_personal (source_type)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_mindscape_personal_updated_at ON mindscape_personal (updated_at DESC)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_mindscape_personal_metadata ON mindscape_personal USING gin (metadata)")


    # mindscape_suggestions table
    if not inspector.has_table("mindscape_suggestions"):
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
    op.execute("CREATE INDEX IF NOT EXISTS idx_suggestions_user ON mindscape_suggestions (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_suggestions_status ON mindscape_suggestions (status)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_suggestions_generated_at ON mindscape_suggestions (generated_at DESC)"
    )

    # playbook_knowledge table
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS playbook_knowledge (
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
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_playbook_knowledge_code ON playbook_knowledge (playbook_code)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_playbook_knowledge_section ON playbook_knowledge (section_type)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_playbook_knowledge_metadata ON playbook_knowledge USING gin (metadata)"
    )

    # external_docs table
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS external_docs (
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

    _upgrade_existing_external_docs_table()

    # Indexes for external_docs
    op.execute("CREATE INDEX IF NOT EXISTS idx_external_docs_user ON external_docs (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_external_docs_source ON external_docs (source_app)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_external_docs_source_id ON external_docs (source_app, source_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_external_docs_metadata ON external_docs USING gin (metadata)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_external_docs_unique_source ON external_docs (user_id, source_app, source_id)"
    )

    # voice_profiles table
    if not inspector.has_table("voice_profiles"):
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
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_voice_profiles_instructor ON voice_profiles (instructor_id)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_voice_profiles_status ON voice_profiles (status)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_voice_profiles_sample_paths ON voice_profiles USING gin (sample_paths)"
    )

    # voice_training_jobs table
    if not inspector.has_table("voice_training_jobs"):
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
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_voice_training_jobs_profile ON voice_training_jobs (voice_profile_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_voice_training_jobs_instructor ON voice_training_jobs (instructor_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_voice_training_jobs_status ON voice_training_jobs (status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_voice_training_jobs_config ON voice_training_jobs USING gin (training_config)"
    )

    # video_segments table
    if not inspector.has_table("video_segments"):
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
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_video_segments_instructor ON video_segments (instructor_id)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_video_segments_course ON video_segments (course_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_video_segments_quality ON video_segments (quality_score DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_video_segments_tags ON video_segments USING gin (tags)"
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
