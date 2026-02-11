"""
Course Production Store

Database operations for voice profiles, training jobs, and video segments
"""

import logging
import psycopg2
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import List, Optional, Dict, Any
from psycopg2.extras import RealDictCursor, Json
from psycopg2.pool import ThreadedConnectionPool

from app.database.config import get_core_postgres_config
from ...models.course_production.voice_profile import (
    VoiceProfile,
    VoiceProfileStatus
)
from ...models.course_production.voice_training_job import (
    VoiceTrainingJob,
    TrainingJobStatus,
    TrainingJobPriority
)
from ...models.course_production.video_segment import (
    VideoSegment,
    ShotType,
    SegmentQuality
)

logger = logging.getLogger(__name__)


class CourseProductionStore:
    """Store for course production data"""

    def __init__(self):
        """Initialize store with PostgreSQL connection"""
        self.pool = None
        self._init_pool()

    def _init_pool(self):
        """Initialize connection pool"""
        try:
            config = get_core_postgres_config()
            self.pool = ThreadedConnectionPool(
                minconn=1,
                maxconn=10,
                host=config.get("host") or "postgres",
                port=config.get("port") or 5432,
                database=config.get("database") or "mindscape_core",
                user=config.get("user") or "mindscape",
                password=config.get("password") or "mindscape_password",
            )
            logger.info("Course production store connection pool initialized")
        except Exception as e:
            logger.error(f"Failed to initialize connection pool: {e}")
            raise

    def _get_connection(self):
        """Get connection from pool"""
        if self.pool is None:
            self._init_pool()
        return self.pool.getconn()

    def _put_connection(self, conn):
        """Return connection to pool"""
        if self.pool:
            self.pool.putconn(conn)

    # Voice Profile operations
    def create_voice_profile(self, profile: VoiceProfile) -> VoiceProfile:
        """Create voice profile"""
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute('''
                    INSERT INTO voice_profiles (
                        id, instructor_id, version, profile_name, status,
                        sample_duration_seconds, sample_count, sample_paths,
                        model_storage_path, model_storage_service, training_job_id,
                        created_at, updated_at, ready_at, quality_score, similarity_score
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                ''', (
                    profile.id, profile.instructor_id, profile.version,
                    profile.profile_name, profile.status.value,
                    profile.sample_duration_seconds, profile.sample_count,
                    Json(profile.sample_paths) if profile.sample_paths else None,
                    profile.model_storage_path, profile.model_storage_service,
                    profile.training_job_id,
                    profile.created_at, profile.updated_at, profile.ready_at,
                    profile.quality_score, profile.similarity_score
                ))
                conn.commit()
                return profile
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create voice profile: {e}")
            raise
        finally:
            self._put_connection(conn)

    def get_voice_profile(self, profile_id: str) -> Optional[VoiceProfile]:
        """Get voice profile by ID"""
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute('SELECT * FROM voice_profiles WHERE id = %s', (profile_id,))
                row = cursor.fetchone()
                if not row:
                    return None
                return self._row_to_voice_profile(row)
        except Exception as e:
            logger.error(f"Failed to get voice profile: {e}")
            raise
        finally:
            self._put_connection(conn)

    def list_voice_profiles(
        self,
        instructor_id: str,
        status_filter: Optional[VoiceProfileStatus] = None
    ) -> List[VoiceProfile]:
        """List voice profiles with optional filter"""
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                if status_filter:
                    cursor.execute('''
                        SELECT * FROM voice_profiles
                        WHERE instructor_id = %s AND status = %s
                        ORDER BY created_at DESC
                    ''', (instructor_id, status_filter.value))
                else:
                    cursor.execute('''
                        SELECT * FROM voice_profiles
                        WHERE instructor_id = %s
                        ORDER BY created_at DESC
                    ''', (instructor_id,))

                rows = cursor.fetchall()
                return [self._row_to_voice_profile(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to list voice profiles: {e}")
            raise
        finally:
            self._put_connection(conn)

    def update_voice_profile(self, profile_id: str, updates: Dict[str, Any]) -> Optional[VoiceProfile]:
        """Update voice profile"""
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                set_clauses = []
                values = []

                for key, value in updates.items():
                    if key == 'sample_paths' and value is not None:
                        set_clauses.append(f"{key} = %s")
                        values.append(Json(value))
                    else:
                        set_clauses.append(f"{key} = %s")
                        values.append(value)

                set_clauses.append("updated_at = %s")
                values.append(_utc_now())
                values.append(profile_id)

                cursor.execute(f'''
                    UPDATE voice_profiles
                    SET {', '.join(set_clauses)}
                    WHERE id = %s
                    RETURNING *
                ''', values)

                row = cursor.fetchone()
                conn.commit()

                if row:
                    return self._row_to_voice_profile(row)
                return None
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update voice profile: {e}")
            raise
        finally:
            self._put_connection(conn)

    def delete_voice_profile(self, profile_id: str) -> bool:
        """Delete voice profile (mark as deprecated)"""
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute('''
                    UPDATE voice_profiles
                    SET status = 'deprecated', updated_at = %s
                    WHERE id = %s
                ''', (_utc_now(), profile_id))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to delete voice profile: {e}")
            raise
        finally:
            self._put_connection(conn)

    # Voice Training Job operations
    def create_training_job(self, job: VoiceTrainingJob) -> VoiceTrainingJob:
        """Create training job"""
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute('''
                    INSERT INTO voice_training_jobs (
                        id, voice_profile_id, instructor_id, status, priority,
                        training_config, sample_file_paths, sample_metadata,
                        started_at, completed_at, estimated_duration_seconds,
                        actual_duration_seconds, result_model_path, result_metrics,
                        error_message, error_stack, gpu_used, compute_cost,
                        created_at, updated_at, log_path
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                ''', (
                    job.id, job.voice_profile_id, job.instructor_id,
                    job.status.value, job.priority.value,
                    Json(job.training_config) if job.training_config else None,
                    Json(job.sample_file_paths) if job.sample_file_paths else None,
                    Json(job.sample_metadata) if job.sample_metadata else None,
                    job.started_at, job.completed_at,
                    job.estimated_duration_seconds, job.actual_duration_seconds,
                    job.result_model_path,
                    Json(job.result_metrics) if job.result_metrics else None,
                    job.error_message, job.error_stack,
                    job.gpu_used, job.compute_cost,
                    job.created_at, job.updated_at, job.log_path
                ))
                conn.commit()
                return job
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create training job: {e}")
            raise
        finally:
            self._put_connection(conn)

    def get_training_job(self, job_id: str) -> Optional[VoiceTrainingJob]:
        """Get training job by ID"""
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute('SELECT * FROM voice_training_jobs WHERE id = %s', (job_id,))
                row = cursor.fetchone()
                if not row:
                    return None
                return self._row_to_training_job(row)
        except Exception as e:
            logger.error(f"Failed to get training job: {e}")
            raise
        finally:
            self._put_connection(conn)

    def list_training_jobs(
        self,
        instructor_id: Optional[str] = None,
        voice_profile_id: Optional[str] = None,
        status_filter: Optional[TrainingJobStatus] = None
    ) -> List[VoiceTrainingJob]:
        """List training jobs with filters"""
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                conditions = []
                values = []

                if instructor_id:
                    conditions.append("instructor_id = %s")
                    values.append(instructor_id)
                if voice_profile_id:
                    conditions.append("voice_profile_id = %s")
                    values.append(voice_profile_id)
                if status_filter:
                    conditions.append("status = %s")
                    values.append(status_filter.value)

                where_clause = " AND ".join(conditions) if conditions else "1=1"

                cursor.execute(f'''
                    SELECT * FROM voice_training_jobs
                    WHERE {where_clause}
                    ORDER BY created_at DESC
                ''', values)

                rows = cursor.fetchall()
                return [self._row_to_training_job(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to list training jobs: {e}")
            raise
        finally:
            self._put_connection(conn)

    def update_training_job(self, job_id: str, updates: Dict[str, Any]) -> Optional[VoiceTrainingJob]:
        """Update training job"""
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                set_clauses = []
                values = []

                for key, value in updates.items():
                    if key in ['training_config', 'sample_file_paths', 'sample_metadata', 'result_metrics']:
                        set_clauses.append(f"{key} = %s")
                        values.append(Json(value) if value is not None else None)
                    else:
                        set_clauses.append(f"{key} = %s")
                        values.append(value)

                set_clauses.append("updated_at = %s")
                values.append(_utc_now())
                values.append(job_id)

                cursor.execute(f'''
                    UPDATE voice_training_jobs
                    SET {', '.join(set_clauses)}
                    WHERE id = %s
                    RETURNING *
                ''', values)

                row = cursor.fetchone()
                conn.commit()

                if row:
                    return self._row_to_training_job(row)
                return None
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update training job: {e}")
            raise
        finally:
            self._put_connection(conn)

    # Video Segment operations
    def create_video_segment(self, segment: VideoSegment) -> VideoSegment:
        """Create video segment"""
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute('''
                    INSERT INTO video_segments (
                        id, instructor_id, course_id, source_video_path, source_video_id,
                        start_time, end_time, duration, segment_file_path,
                        shot_type, quality_score, quality_level,
                        tags, action_names, intent_tags,
                        script_line_ids, script_alignment_confidence,
                        pose_estimation, composition_features,
                        lighting_quality, framing_quality,
                        transcript, transcript_confidence,
                        usage_count, last_used_at,
                        created_at, updated_at, analysis_job_id
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                ''', (
                    segment.id, segment.instructor_id, segment.course_id,
                    segment.source_video_path, segment.source_video_id,
                    segment.start_time, segment.end_time, segment.duration,
                    segment.segment_file_path,
                    segment.shot_type.value if segment.shot_type else None,
                    segment.quality_score,
                    segment.quality_level.value,
                    Json(segment.tags) if segment.tags else None,
                    Json(segment.action_names) if segment.action_names else None,
                    Json(segment.intent_tags) if segment.intent_tags else None,
                    Json(segment.script_line_ids) if segment.script_line_ids else None,
                    segment.script_alignment_confidence,
                    Json(segment.pose_estimation) if segment.pose_estimation else None,
                    Json(segment.composition_features) if segment.composition_features else None,
                    segment.lighting_quality, segment.framing_quality,
                    segment.transcript, segment.transcript_confidence,
                    segment.usage_count, segment.last_used_at,
                    segment.created_at, segment.updated_at, segment.analysis_job_id
                ))
                conn.commit()
                return segment
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create video segment: {e}")
            raise
        finally:
            self._put_connection(conn)

    def get_video_segment(self, segment_id: str) -> Optional[VideoSegment]:
        """Get video segment by ID"""
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute('SELECT * FROM video_segments WHERE id = %s', (segment_id,))
                row = cursor.fetchone()
                if not row:
                    return None
                return self._row_to_video_segment(row)
        except Exception as e:
            logger.error(f"Failed to get video segment: {e}")
            raise
        finally:
            self._put_connection(conn)

    def list_video_segments(
        self,
        instructor_id: str,
        course_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        shot_type: Optional[ShotType] = None,
        min_quality: Optional[float] = None,
        script_line_id: Optional[str] = None
    ) -> List[VideoSegment]:
        """List video segments with filters"""
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                conditions = ["instructor_id = %s"]
                values = [instructor_id]

                if course_id:
                    conditions.append("course_id = %s")
                    values.append(course_id)
                if shot_type:
                    conditions.append("shot_type = %s")
                    values.append(shot_type.value)
                if min_quality is not None:
                    conditions.append("quality_score >= %s")
                    values.append(min_quality)

                where_clause = " AND ".join(conditions)

                cursor.execute(f'''
                    SELECT * FROM video_segments
                    WHERE {where_clause}
                    ORDER BY created_at DESC
                ''', values)

                rows = cursor.fetchall()
                segments = [self._row_to_video_segment(row) for row in rows]

                # Apply tag and script_line_id filters in Python (for JSONB queries)
                if tags:
                    segments = [s for s in segments if any(tag in s.tags for tag in tags)]
                if script_line_id:
                    segments = [s for s in segments if script_line_id in s.script_line_ids]

                return segments
        except Exception as e:
            logger.error(f"Failed to list video segments: {e}")
            raise
        finally:
            self._put_connection(conn)

    def update_video_segment(self, segment_id: str, updates: Dict[str, Any]) -> Optional[VideoSegment]:
        """Update video segment"""
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                set_clauses = []
                values = []

                for key, value in updates.items():
                    if key in ['tags', 'action_names', 'intent_tags', 'script_line_ids', 'pose_estimation', 'composition_features']:
                        set_clauses.append(f"{key} = %s")
                        values.append(Json(value) if value is not None else None)
                    else:
                        set_clauses.append(f"{key} = %s")
                        values.append(value)

                set_clauses.append("updated_at = %s")
                values.append(_utc_now())
                values.append(segment_id)

                cursor.execute(f'''
                    UPDATE video_segments
                    SET {', '.join(set_clauses)}
                    WHERE id = %s
                    RETURNING *
                ''', values)

                row = cursor.fetchone()
                conn.commit()

                if row:
                    return self._row_to_video_segment(row)
                return None
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update video segment: {e}")
            raise
        finally:
            self._put_connection(conn)

    def delete_video_segment(self, segment_id: str) -> bool:
        """Delete video segment"""
        conn = self._get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute('DELETE FROM video_segments WHERE id = %s', (segment_id,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to delete video segment: {e}")
            raise
        finally:
            self._put_connection(conn)

    # Helper methods to convert rows to models
    def _row_to_voice_profile(self, row: Dict[str, Any]) -> VoiceProfile:
        """Convert database row to VoiceProfile model"""
        return VoiceProfile(
            id=str(row['id']),
            instructor_id=row['instructor_id'],
            version=row['version'],
            profile_name=row['profile_name'],
            status=VoiceProfileStatus(row['status']),
            sample_duration_seconds=row['sample_duration_seconds'],
            sample_count=row['sample_count'],
            sample_paths=row['sample_paths'] if row['sample_paths'] else [],
            model_storage_path=row['model_storage_path'],
            model_storage_service=row['model_storage_service'],
            training_job_id=str(row['training_job_id']) if row['training_job_id'] else None,
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            ready_at=row['ready_at'],
            quality_score=row['quality_score'],
            similarity_score=row['similarity_score']
        )

    def _row_to_training_job(self, row: Dict[str, Any]) -> VoiceTrainingJob:
        """Convert database row to VoiceTrainingJob model"""
        return VoiceTrainingJob(
            id=str(row['id']),
            voice_profile_id=str(row['voice_profile_id']),
            instructor_id=row['instructor_id'],
            status=TrainingJobStatus(row['status']),
            priority=TrainingJobPriority(row['priority']),
            training_config=row['training_config'] if row['training_config'] else {},
            sample_file_paths=row['sample_file_paths'] if row['sample_file_paths'] else [],
            sample_metadata=row['sample_metadata'] if row['sample_metadata'] else [],
            started_at=row['started_at'],
            completed_at=row['completed_at'],
            estimated_duration_seconds=row['estimated_duration_seconds'],
            actual_duration_seconds=row['actual_duration_seconds'],
            result_model_path=row['result_model_path'],
            result_metrics=row['result_metrics'],
            error_message=row['error_message'],
            error_stack=row['error_stack'],
            gpu_used=row['gpu_used'],
            compute_cost=row['compute_cost'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            log_path=row['log_path']
        )

    def _row_to_video_segment(self, row: Dict[str, Any]) -> VideoSegment:
        """Convert database row to VideoSegment model"""
        return VideoSegment(
            id=str(row['id']),
            instructor_id=row['instructor_id'],
            course_id=str(row['course_id']) if row['course_id'] else None,
            source_video_path=row['source_video_path'],
            source_video_id=row['source_video_id'],
            start_time=row['start_time'],
            end_time=row['end_time'],
            duration=row['duration'],
            segment_file_path=row['segment_file_path'],
            shot_type=ShotType(row['shot_type']) if row['shot_type'] else None,
            quality_score=row['quality_score'],
            quality_level=SegmentQuality(row['quality_level']),
            tags=row['tags'] if row['tags'] else [],
            action_names=row['action_names'] if row['action_names'] else [],
            intent_tags=row['intent_tags'] if row['intent_tags'] else [],
            script_line_ids=row['script_line_ids'] if row['script_line_ids'] else [],
            script_alignment_confidence=row['script_alignment_confidence'],
            pose_estimation=row['pose_estimation'],
            composition_features=row['composition_features'],
            lighting_quality=row['lighting_quality'],
            framing_quality=row['framing_quality'],
            transcript=row['transcript'],
            transcript_confidence=row['transcript_confidence'],
            usage_count=row['usage_count'],
            last_used_at=row['last_used_at'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            analysis_job_id=str(row['analysis_job_id']) if row['analysis_job_id'] else None
        )
