"""
Validate vector database schema for mindscape seed and suggestion system.
Run this on service startup to verify migrations are applied.
"""

import logging

try:
    import psycopg2
except ImportError:
    psycopg2 = None

logger = logging.getLogger(__name__)


def init_mindscape_tables():
    """Validate vector database schema managed by Alembic."""
    if psycopg2 is None:
        logger.warning("psycopg2 not available; skipping vector DB validation.")
        return False

    conn = None
    try:
        from app.database.config import get_vector_postgres_config

        postgres_config = get_vector_postgres_config()
        conn = psycopg2.connect(**postgres_config)
        cursor = conn.cursor()

        cursor.execute("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        has_vector = cursor.fetchone() is not None

        cursor.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        )
        existing_tables = {row[0] for row in cursor.fetchall()}

        required_tables = {
            "mindscape_personal",
            "mindscape_suggestions",
            "playbook_knowledge",
            "external_docs",
        }

        missing_tables = sorted(required_tables - existing_tables)

        if not has_vector:
            logger.error("pgvector extension is missing in vector database.")
        if missing_tables:
            logger.error(f"Missing vector tables: {', '.join(missing_tables)}")

        if not has_vector or missing_tables:
            logger.error(
                "Vector database schema is not ready. Run: "
                "alembic -c backend/alembic.ini upgrade head"
            )
            return False

        logger.info("Vector database schema validated successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to validate vector schema: {e}", exc_info=True)
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _init_course_production_tables(cursor):
    """Initialize course production tables"""
    # Voice profiles table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS voice_profiles (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            instructor_id TEXT NOT NULL,
            version INTEGER DEFAULT 1,
            profile_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            sample_duration_seconds REAL,
            sample_count INTEGER DEFAULT 0,
            sample_paths JSONB,
            model_storage_path TEXT,
            model_storage_service TEXT,
            training_job_id UUID,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            ready_at TIMESTAMP,
            quality_score REAL,
            similarity_score REAL
        )
    """
    )

    # Voice training jobs table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS voice_training_jobs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            voice_profile_id UUID NOT NULL,
            instructor_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            priority TEXT NOT NULL DEFAULT 'normal',
            training_config JSONB,
            sample_file_paths JSONB,
            sample_metadata JSONB,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            estimated_duration_seconds INTEGER,
            actual_duration_seconds INTEGER,
            result_model_path TEXT,
            result_metrics JSONB,
            error_message TEXT,
            error_stack TEXT,
            gpu_used TEXT,
            compute_cost REAL,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            log_path TEXT,
            FOREIGN KEY (voice_profile_id) REFERENCES voice_profiles (id)
        )
    """
    )

    # Video segments table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS video_segments (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            instructor_id TEXT NOT NULL,
            course_id UUID,
            source_video_path TEXT NOT NULL,
            source_video_id TEXT NOT NULL,
            start_time REAL NOT NULL,
            end_time REAL NOT NULL,
            duration REAL NOT NULL,
            segment_file_path TEXT,
            shot_type TEXT,
            quality_score REAL DEFAULT 0.0,
            quality_level TEXT DEFAULT 'fair',
            tags JSONB,
            action_names JSONB,
            intent_tags JSONB,
            script_line_ids JSONB,
            script_alignment_confidence REAL,
            pose_estimation JSONB,
            composition_features JSONB,
            lighting_quality REAL,
            framing_quality REAL,
            transcript TEXT,
            transcript_confidence REAL,
            usage_count INTEGER DEFAULT 0,
            last_used_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            analysis_job_id UUID
        )
    """
    )

    # Create indexes for voice_profiles
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_voice_profiles_instructor
        ON voice_profiles(instructor_id)
    """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_voice_profiles_status
        ON voice_profiles(status)
    """
    )

    # Create indexes for voice_training_jobs
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_voice_training_jobs_profile
        ON voice_training_jobs(voice_profile_id)
    """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_voice_training_jobs_instructor
        ON voice_training_jobs(instructor_id)
    """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_voice_training_jobs_status
        ON voice_training_jobs(status)
    """
    )

    # Create indexes for video_segments
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_video_segments_instructor
        ON video_segments(instructor_id)
    """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_video_segments_course
        ON video_segments(course_id)
    """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_video_segments_quality
        ON video_segments(quality_score DESC)
    """
    )

    # GIN indexes for JSONB columns
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_voice_profiles_sample_paths
        ON voice_profiles USING gin(sample_paths)
    """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_voice_training_jobs_config
        ON voice_training_jobs USING gin(training_config)
    """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_video_segments_tags
        ON video_segments USING gin(tags)
    """
    )

    logger.info("Course production tables initialized")


if __name__ == "__main__":
    init_mindscape_tables()
