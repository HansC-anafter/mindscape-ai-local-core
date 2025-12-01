"""
Initialize database tables for mindscape seed and suggestion system
Run this on service startup to ensure tables exist
"""

import os
import logging
import psycopg2

logger = logging.getLogger(__name__)


def init_mindscape_tables():
    """Initialize mindscape seed and suggestion tables in PostgreSQL"""
    try:
        postgres_config = {
            "host": os.getenv("POSTGRES_HOST", "postgres"),
            "port": int(os.getenv("POSTGRES_PORT", "5432")),
            "database": os.getenv("POSTGRES_DB", "mindscape_vectors"),
            "user": os.getenv("POSTGRES_USER", "mindscape"),
            "password": os.getenv("POSTGRES_PASSWORD", "mindscape_password"),
        }

        conn = psycopg2.connect(**postgres_config)
        cursor = conn.cursor()

        # Ensure pgvector extension
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
        logger.info("pgvector extension ensured")

        # Create mindscape_personal table (renamed from seed_log)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS mindscape_personal (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id TEXT NOT NULL DEFAULT 'default_user',

                -- Content source
                source_type TEXT NOT NULL,  -- 'self_profile' / 'intent' / 'task' / 'weekly_review' / 'daily_journal' / 'reflection'
                content TEXT NOT NULL,
                metadata JSONB,

                -- Source information (kept for compatibility)
                source_id TEXT,
                source_context TEXT,

                -- Confidence and weight
                confidence REAL DEFAULT 0.5,
                weight REAL DEFAULT 1.0,

                -- Vector embedding (pgvector)
                embedding vector(1536),  -- OpenAI text-embedding-3-small

                -- Timestamps
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        ''')

        # Create indexes for mindscape_personal
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_mindscape_personal_user
            ON mindscape_personal(user_id)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_mindscape_personal_source
            ON mindscape_personal(source_type)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_mindscape_personal_updated_at
            ON mindscape_personal(updated_at DESC)
        ''')

        # GIN index for metadata
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_mindscape_personal_metadata
            ON mindscape_personal USING gin(metadata)
        ''')

        # Create vector index (only if there are embeddings)
        try:
            cursor.execute('SELECT COUNT(*) FROM mindscape_personal WHERE embedding IS NOT NULL')
            count = cursor.fetchone()[0]
            if count > 0:
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_mindscape_personal_embedding
                    ON mindscape_personal
                    USING ivfflat (embedding vector_cosine_ops)
                    WITH (lists = 100)
                ''')
        except Exception as e:
            logger.warning(f"Could not create vector index: {e}")

        # Create suggestions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS mindscape_suggestions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id TEXT NOT NULL DEFAULT 'default_user',

                -- Suggestion content
                suggestion_type TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                suggested_data JSONB,

                -- Source information
                source_seed_ids UUID[],
                source_summary TEXT,
                confidence REAL NOT NULL,

                -- Status
                status TEXT DEFAULT 'pending',
                reviewed_at TIMESTAMP,
                reviewed_by TEXT,

                -- Timestamps
                generated_at TIMESTAMP DEFAULT NOW(),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        ''')

        # Create indexes for suggestions
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_suggestions_user
            ON mindscape_suggestions(user_id)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_suggestions_status
            ON mindscape_suggestions(status)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_suggestions_generated_at
            ON mindscape_suggestions(generated_at DESC)
        ''')

        # Create playbook_knowledge table
        cursor.execute('''
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
        ''')

        # Create indexes for playbook_knowledge
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_playbook_knowledge_code
            ON playbook_knowledge(playbook_code)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_playbook_knowledge_section
            ON playbook_knowledge(section_type)
        ''')

        # GIN index for metadata
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_playbook_knowledge_metadata
            ON playbook_knowledge USING gin(metadata)
        ''')

        # Create vector index for playbook_knowledge (only if data exists)
        try:
            cursor.execute('SELECT COUNT(*) FROM playbook_knowledge WHERE embedding IS NOT NULL')
            count = cursor.fetchone()[0]
            if count > 0:
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_playbook_knowledge_embedding
                    ON playbook_knowledge
                    USING ivfflat (embedding vector_cosine_ops)
                    WITH (lists = 50)
                ''')
        except Exception as e:
            logger.warning(f"Could not create playbook vector index: {e}")

        # Create external_docs table
        cursor.execute('''
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
        ''')

        # Create indexes for external_docs
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_external_docs_user
            ON external_docs(user_id)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_external_docs_source
            ON external_docs(source_app)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_external_docs_source_id
            ON external_docs(source_app, source_id)
        ''')

        # GIN index for metadata
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_external_docs_metadata
            ON external_docs USING gin(metadata)
        ''')

        # Unique constraint: same document from same source cannot be duplicated
        cursor.execute('''
            CREATE UNIQUE INDEX IF NOT EXISTS idx_external_docs_unique_source
            ON external_docs(user_id, source_app, source_id)
        ''')

        # Create vector index for external_docs (only if data exists)
        try:
            cursor.execute('SELECT COUNT(*) FROM external_docs WHERE embedding IS NOT NULL')
            count = cursor.fetchone()[0]
            if count > 0:
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_external_docs_embedding
                    ON external_docs
                    USING ivfflat (embedding vector_cosine_ops)
                    WITH (lists = 100)
                ''')
        except Exception as e:
            logger.warning(f"Could not create external_docs vector index: {e}")

        # Create course_production tables
        _init_course_production_tables(cursor)

        conn.commit()
        conn.close()

        logger.info("Mindscape database tables initialized successfully")
        return True

    except Exception as e:
        logger.error(f"Failed to initialize mindscape tables: {e}", exc_info=True)
        return False


def _init_course_production_tables(cursor):
    """Initialize course production tables"""
    # Voice profiles table
    cursor.execute('''
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
    ''')

    # Voice training jobs table
    cursor.execute('''
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
    ''')

    # Video segments table
    cursor.execute('''
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
    ''')

    # Create indexes for voice_profiles
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_voice_profiles_instructor
        ON voice_profiles(instructor_id)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_voice_profiles_status
        ON voice_profiles(status)
    ''')

    # Create indexes for voice_training_jobs
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_voice_training_jobs_profile
        ON voice_training_jobs(voice_profile_id)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_voice_training_jobs_instructor
        ON voice_training_jobs(instructor_id)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_voice_training_jobs_status
        ON voice_training_jobs(status)
    ''')

    # Create indexes for video_segments
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_video_segments_instructor
        ON video_segments(instructor_id)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_video_segments_course
        ON video_segments(course_id)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_video_segments_quality
        ON video_segments(quality_score DESC)
    ''')

    # GIN indexes for JSONB columns
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_voice_profiles_sample_paths
        ON voice_profiles USING gin(sample_paths)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_voice_training_jobs_config
        ON voice_training_jobs USING gin(training_config)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_video_segments_tags
        ON video_segments USING gin(tags)
    ''')

    logger.info("Course production tables initialized")


if __name__ == "__main__":
    init_mindscape_tables()

