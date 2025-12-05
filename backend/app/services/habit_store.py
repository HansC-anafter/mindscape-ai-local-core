"""
Habit Learning Data Store Service
處理習慣觀察、候選習慣和審計記錄的資料持久化
"""

import os
import json
import sqlite3
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from contextlib import contextmanager
import logging

from backend.app.models.habit import (
    HabitObservation,
    HabitCandidate,
    HabitAuditLog,
    HabitCategory,
    HabitCandidateStatus,
    HabitAuditAction,
)
from backend.app.models.mindscape import MindscapeProfile, UserPreferences

logger = logging.getLogger(__name__)


class HabitStore:
    """習慣學習資料存儲服務"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            # Use /app/data/mindscape.db in Docker, otherwise backend/data/mindscape.db
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            data_dir = os.path.join(base_dir, "data")
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, "mindscape.db")

        self.db_path = db_path

    @contextmanager
    def get_connection(self):
        """Get database connection with proper cleanup"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # Habit Observation methods

    def create_observation(self, observation: HabitObservation) -> HabitObservation:
        """Create habit observation record"""
        # Ensure database schema is up to date
        self._ensure_observation_schema()

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO habit_observations (
                    id, profile_id, habit_key, habit_value, habit_category,
                    source_type, source_id, source_context,
                    has_insight_signal, insight_score,
                    observed_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                observation.id,
                observation.profile_id,
                observation.habit_key,
                observation.habit_value,
                observation.habit_category.value,
                observation.source_type,
                observation.source_id,
                json.dumps(observation.source_context) if observation.source_context else None,
                1 if observation.has_insight_signal else 0,
                observation.insight_score,
                observation.observed_at.isoformat(),
                observation.created_at.isoformat(),
            ))
            conn.commit()
            return observation

    def get_observations(
        self,
        profile_id: str,
        habit_key: Optional[str] = None,
        limit: int = 100
    ) -> List[HabitObservation]:
        """取得習慣觀察記錄"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = 'SELECT * FROM habit_observations WHERE profile_id = ?'
            params = [profile_id]

            if habit_key:
                query += ' AND habit_key = ?'
                params.append(habit_key)

            query += ' ORDER BY observed_at DESC LIMIT ?'
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_observation(row) for row in rows]

    def count_observations(
        self,
        profile_id: str,
        habit_key: str,
        habit_value: str,
        recent_n: int = 10
    ) -> int:
        """計算最近 N 次觀察中特定 key-value 的出現次數"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) FROM (
                    SELECT * FROM habit_observations
                    WHERE profile_id = ? AND habit_key = ? AND habit_value = ?
                    ORDER BY observed_at DESC
                    LIMIT ?
                )
            ''', (profile_id, habit_key, habit_value, recent_n))
            return cursor.fetchone()[0]

    # Habit Candidate methods

    def create_candidate(self, candidate: HabitCandidate) -> HabitCandidate:
        """建立候選習慣"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO habit_candidates (
                    id, profile_id, habit_key, habit_value, habit_category,
                    evidence_count, confidence, first_seen_at, last_seen_at,
                    evidence_refs, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                candidate.id,
                candidate.profile_id,
                candidate.habit_key,
                candidate.habit_value,
                candidate.habit_category.value,
                candidate.evidence_count,
                candidate.confidence,
                candidate.first_seen_at.isoformat() if candidate.first_seen_at else None,
                candidate.last_seen_at.isoformat() if candidate.last_seen_at else None,
                json.dumps(candidate.evidence_refs),
                candidate.status.value,
                candidate.created_at.isoformat(),
                candidate.updated_at.isoformat(),
            ))
            conn.commit()
            return candidate

    def get_candidate(
        self,
        profile_id: str,
        habit_key: str,
        habit_value: str
    ) -> Optional[HabitCandidate]:
        """取得特定的候選習慣"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM habit_candidates
                WHERE profile_id = ? AND habit_key = ? AND habit_value = ?
            ''', (profile_id, habit_key, habit_value))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_candidate(row)

    def update_candidate(self, candidate: HabitCandidate) -> HabitCandidate:
        """更新候選習慣"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE habit_candidates
                SET evidence_count = ?, confidence = ?, first_seen_at = ?,
                    last_seen_at = ?, evidence_refs = ?, status = ?,
                    updated_at = ?
                WHERE id = ?
            ''', (
                candidate.evidence_count,
                candidate.confidence,
                candidate.first_seen_at.isoformat() if candidate.first_seen_at else None,
                candidate.last_seen_at.isoformat() if candidate.last_seen_at else None,
                json.dumps(candidate.evidence_refs),
                candidate.status.value,
                candidate.updated_at.isoformat(),
                candidate.id,
            ))
            conn.commit()
            return candidate

    def get_candidates(
        self,
        profile_id: str,
        status: Optional[HabitCandidateStatus] = None,
        limit: int = 50
    ) -> List[HabitCandidate]:
        """取得候選習慣列表"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = 'SELECT * FROM habit_candidates WHERE profile_id = ?'
            params = [profile_id]

            if status:
                query += ' AND status = ?'
                params.append(status.value)

            query += ' ORDER BY confidence DESC, created_at DESC LIMIT ?'
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_candidate(row) for row in rows]

    def get_confirmed_habits(self, profile_id: str) -> List[HabitCandidate]:
        """取得已確認的習慣"""
        return self.get_candidates(profile_id, status=HabitCandidateStatus.CONFIRMED)

    # Habit Audit Log methods

    def create_audit_log(self, audit_log: HabitAuditLog) -> HabitAuditLog:
        """建立審計記錄"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO habit_audit_logs (
                    id, profile_id, candidate_id, action, previous_status,
                    new_status, actor_type, actor_id, reason, metadata, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                audit_log.id,
                audit_log.profile_id,
                audit_log.candidate_id,
                audit_log.action.value,
                audit_log.previous_status.value if audit_log.previous_status else None,
                audit_log.new_status.value if audit_log.new_status else None,
                audit_log.actor_type,
                audit_log.actor_id,
                audit_log.reason,
                json.dumps(audit_log.metadata) if audit_log.metadata else None,
                audit_log.created_at.isoformat(),
            ))
            conn.commit()
            return audit_log

    def get_audit_logs(
        self,
        profile_id: str,
        candidate_id: Optional[str] = None,
        limit: int = 100
    ) -> List[HabitAuditLog]:
        """取得審計記錄"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = 'SELECT * FROM habit_audit_logs WHERE profile_id = ?'
            params = [profile_id]

            if candidate_id:
                query += ' AND candidate_id = ?'
                params.append(candidate_id)

            query += ' ORDER BY created_at DESC LIMIT ?'
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_audit_log(row) for row in rows]

    # Helper methods

    def apply_confirmed_habits(self, profile: MindscapeProfile) -> MindscapeProfile:
        """
        Apply confirmed habits to profile preferences
        Don't modify original settings, only overlay during reading
        """
        confirmed_habits = self.get_confirmed_habits(profile.id)
        if not confirmed_habits:
            return profile

        # Create a copy of preferences (avoid modifying original object)
        preferences_dict = profile.preferences.dict() if profile.preferences else {}

        # Apply confirmed habits
        for habit in confirmed_habits:
            if habit.habit_category == HabitCategory.PREFERENCE:
                # Directly override corresponding preference settings
                if habit.habit_key in ['language', 'communication_style', 'response_length', 'timezone']:
                    preferences_dict[habit.habit_key] = habit.habit_value

        # Create new UserPreferences object
        from backend.app.models.mindscape import UserPreferences, CommunicationStyle, ResponseLength
        updated_preferences = UserPreferences(**preferences_dict)

        # Create new profile copy (don't modify original object)
        profile_dict = profile.dict()
        profile_dict['preferences'] = updated_preferences
        return MindscapeProfile(**profile_dict)

    def _row_to_observation(self, row) -> HabitObservation:
        """Convert database row to HabitObservation"""
        # Backward compatibility (if new fields don't exist)
        has_insight_signal = row.get('has_insight_signal', 0) == 1 if 'has_insight_signal' in row.keys() else False
        insight_score = row.get('insight_score', 0.0) if 'insight_score' in row.keys() else 0.0

        return HabitObservation(
            id=row['id'],
            profile_id=row['profile_id'],
            habit_key=row['habit_key'],
            habit_value=row['habit_value'],
            habit_category=HabitCategory(row['habit_category']),
            source_type=row['source_type'],
            source_id=row['source_id'],
            source_context=json.loads(row['source_context']) if row['source_context'] else None,
            has_insight_signal=has_insight_signal,
            insight_score=insight_score,
            observed_at=datetime.fromisoformat(row['observed_at']),
            created_at=datetime.fromisoformat(row['created_at']),
        )

    def _ensure_observation_schema(self):
        """Ensure habit_observations table has new fields (migration)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Check if columns exist
            cursor.execute("PRAGMA table_info(habit_observations)")
            columns = [row[1] for row in cursor.fetchall()]

            # Add has_insight_signal column (if not exists)
            if 'has_insight_signal' not in columns:
                try:
                    cursor.execute('''
                        ALTER TABLE habit_observations
                        ADD COLUMN has_insight_signal INTEGER DEFAULT 0
                    ''')
                    logger.info("Added has_insight_signal column to habit_observations table")
                except sqlite3.OperationalError as e:
                    logger.warning(f"Failed to add has_insight_signal column: {e}")

            # Add insight_score column (if not exists)
            if 'insight_score' not in columns:
                try:
                    cursor.execute('''
                        ALTER TABLE habit_observations
                        ADD COLUMN insight_score REAL DEFAULT 0.0
                    ''')
                    logger.info("Added insight_score column to habit_observations table")
                except sqlite3.OperationalError as e:
                    logger.warning(f"Failed to add insight_score column: {e}")

            conn.commit()

    def _row_to_candidate(self, row) -> HabitCandidate:
        """將資料庫行轉換為 HabitCandidate"""
        return HabitCandidate(
            id=row['id'],
            profile_id=row['profile_id'],
            habit_key=row['habit_key'],
            habit_value=row['habit_value'],
            habit_category=HabitCategory(row['habit_category']),
            evidence_count=row['evidence_count'],
            confidence=row['confidence'],
            first_seen_at=datetime.fromisoformat(row['first_seen_at']) if row['first_seen_at'] else None,
            last_seen_at=datetime.fromisoformat(row['last_seen_at']) if row['last_seen_at'] else None,
            evidence_refs=json.loads(row['evidence_refs'] or '[]'),
            status=HabitCandidateStatus(row['status']),
            created_at=datetime.fromisoformat(row['created_at']),
            updated_at=datetime.fromisoformat(row['updated_at']),
        )

    def _row_to_audit_log(self, row) -> HabitAuditLog:
        """將資料庫行轉換為 HabitAuditLog"""
        return HabitAuditLog(
            id=row['id'],
            profile_id=row['profile_id'],
            candidate_id=row['candidate_id'],
            action=HabitAuditAction(row['action']),
            previous_status=HabitCandidateStatus(row['previous_status']) if row['previous_status'] else None,
            new_status=HabitCandidateStatus(row['new_status']) if row['new_status'] else None,
            actor_type=row['actor_type'],
            actor_id=row['actor_id'],
            reason=row['reason'],
            metadata=json.loads(row['metadata']) if row['metadata'] else None,
            created_at=datetime.fromisoformat(row['created_at']),
        )
