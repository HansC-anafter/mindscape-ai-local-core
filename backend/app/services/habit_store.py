"""
Habit Learning Data Store Service
Handles habit observations, candidates, and audit records persistence.
"""

import logging
from datetime import datetime


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import List, Optional, Dict, Any

from sqlalchemy import text

from backend.app.models.habit import (
    HabitObservation,
    HabitCandidate,
    HabitAuditLog,
    HabitCategory,
    HabitCandidateStatus,
    HabitAuditAction,
)
from backend.app.models.mindscape import MindscapeProfile
from backend.app.services.stores.postgres_base import PostgresStoreBase

logger = logging.getLogger(__name__)


class HabitStore(PostgresStoreBase):
    """Habit learning data store service."""

    def __init__(self, db_path: Optional[str] = None, db_role: str = "core"):
        super().__init__(db_role=db_role)
        self.db_path = db_path
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Validate required tables exist (managed by Alembic migrations)."""
        required_tables = {
            "habit_observations",
            "habit_candidates",
            "habit_audit_logs",
        }
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
                )
            ).fetchall()
            existing = {row.table_name for row in rows}

        missing = required_tables - existing
        if missing:
            missing_str = ", ".join(sorted(missing))
            raise RuntimeError(
                "Missing PostgreSQL tables: "
                f"{missing_str}. Run: alembic -c backend/alembic.ini upgrade head"
            )

    def create_observation(self, observation: HabitObservation) -> HabitObservation:
        """Create habit observation record."""
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO habit_observations (
                        id, profile_id, habit_key, habit_value, habit_category,
                        source_type, source_id, source_context,
                        has_insight_signal, insight_score,
                        observed_at, created_at
                    ) VALUES (
                        :id, :profile_id, :habit_key, :habit_value, :habit_category,
                        :source_type, :source_id, :source_context,
                        :has_insight_signal, :insight_score,
                        :observed_at, :created_at
                    )
                """
                ),
                {
                    "id": observation.id,
                    "profile_id": observation.profile_id,
                    "habit_key": observation.habit_key,
                    "habit_value": observation.habit_value,
                    "habit_category": observation.habit_category.value,
                    "source_type": observation.source_type,
                    "source_id": observation.source_id,
                    "source_context": self.serialize_json(observation.source_context)
                    if observation.source_context
                    else None,
                    "has_insight_signal": observation.has_insight_signal,
                    "insight_score": observation.insight_score,
                    "observed_at": observation.observed_at,
                    "created_at": observation.created_at,
                },
            )
            return observation

    def get_observations(
        self,
        profile_id: str,
        habit_key: Optional[str] = None,
        limit: int = 100,
    ) -> List[HabitObservation]:
        """Get habit observation records."""
        query = "SELECT * FROM habit_observations WHERE profile_id = :profile_id"
        params: Dict[str, Any] = {"profile_id": profile_id, "limit": limit}

        if habit_key:
            query += " AND habit_key = :habit_key"
            params["habit_key"] = habit_key

        query += " ORDER BY observed_at DESC LIMIT :limit"

        with self.get_connection() as conn:
            rows = conn.execute(text(query), params).fetchall()
            return [self._row_to_observation(row) for row in rows]

    def count_observations(
        self,
        profile_id: str,
        habit_key: str,
        habit_value: str,
        recent_n: int = 10,
    ) -> int:
        """Count occurrences of key-value in the most recent observations."""
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT COUNT(*) AS count FROM (
                        SELECT id FROM habit_observations
                        WHERE profile_id = :profile_id
                          AND habit_key = :habit_key
                          AND habit_value = :habit_value
                        ORDER BY observed_at DESC
                        LIMIT :limit
                    ) AS recent
                """
                ),
                {
                    "profile_id": profile_id,
                    "habit_key": habit_key,
                    "habit_value": habit_value,
                    "limit": recent_n,
                },
            ).fetchone()
            return int(row.count or 0) if row else 0

    def create_candidate(self, candidate: HabitCandidate) -> HabitCandidate:
        """Create a habit candidate."""
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO habit_candidates (
                        id, profile_id, habit_key, habit_value, habit_category,
                        evidence_count, confidence, first_seen_at, last_seen_at,
                        evidence_refs, status, created_at, updated_at
                    ) VALUES (
                        :id, :profile_id, :habit_key, :habit_value, :habit_category,
                        :evidence_count, :confidence, :first_seen_at, :last_seen_at,
                        :evidence_refs, :status, :created_at, :updated_at
                    )
                """
                ),
                {
                    "id": candidate.id,
                    "profile_id": candidate.profile_id,
                    "habit_key": candidate.habit_key,
                    "habit_value": candidate.habit_value,
                    "habit_category": candidate.habit_category.value,
                    "evidence_count": candidate.evidence_count,
                    "confidence": candidate.confidence,
                    "first_seen_at": candidate.first_seen_at,
                    "last_seen_at": candidate.last_seen_at,
                    "evidence_refs": self.serialize_json(candidate.evidence_refs),
                    "status": candidate.status.value,
                    "created_at": candidate.created_at,
                    "updated_at": candidate.updated_at,
                },
            )
            return candidate

    def get_candidate(
        self, profile_id: str, habit_key: str, habit_value: str
    ) -> Optional[HabitCandidate]:
        """Get a specific habit candidate."""
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT * FROM habit_candidates
                    WHERE profile_id = :profile_id
                      AND habit_key = :habit_key
                      AND habit_value = :habit_value
                """
                ),
                {
                    "profile_id": profile_id,
                    "habit_key": habit_key,
                    "habit_value": habit_value,
                },
            ).fetchone()

        if not row:
            return None

        return self._row_to_candidate(row)

    def update_candidate(self, candidate: HabitCandidate) -> HabitCandidate:
        """Update habit candidate."""
        candidate.updated_at = _utc_now()
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    UPDATE habit_candidates
                    SET evidence_count = :evidence_count,
                        confidence = :confidence,
                        first_seen_at = :first_seen_at,
                        last_seen_at = :last_seen_at,
                        evidence_refs = :evidence_refs,
                        status = :status,
                        updated_at = :updated_at
                    WHERE id = :id
                """
                ),
                {
                    "evidence_count": candidate.evidence_count,
                    "confidence": candidate.confidence,
                    "first_seen_at": candidate.first_seen_at,
                    "last_seen_at": candidate.last_seen_at,
                    "evidence_refs": self.serialize_json(candidate.evidence_refs),
                    "status": candidate.status.value,
                    "updated_at": candidate.updated_at,
                    "id": candidate.id,
                },
            )
            return candidate

    def get_candidates(
        self,
        profile_id: str,
        status: Optional[HabitCandidateStatus] = None,
        limit: int = 50,
    ) -> List[HabitCandidate]:
        """Get habit candidates list."""
        query = "SELECT * FROM habit_candidates WHERE profile_id = :profile_id"
        params: Dict[str, Any] = {"profile_id": profile_id, "limit": limit}

        if status:
            query += " AND status = :status"
            params["status"] = status.value

        query += " ORDER BY confidence DESC, created_at DESC LIMIT :limit"

        with self.get_connection() as conn:
            rows = conn.execute(text(query), params).fetchall()
            return [self._row_to_candidate(row) for row in rows]

    def get_confirmed_habits(self, profile_id: str) -> List[HabitCandidate]:
        """Get confirmed habits."""
        return self.get_candidates(profile_id, status=HabitCandidateStatus.CONFIRMED)

    def create_audit_log(self, audit_log: HabitAuditLog) -> HabitAuditLog:
        """Create audit log entry."""
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO habit_audit_logs (
                        id, profile_id, candidate_id, action, previous_status,
                        new_status, actor_type, actor_id, reason, metadata, created_at
                    ) VALUES (
                        :id, :profile_id, :candidate_id, :action, :previous_status,
                        :new_status, :actor_type, :actor_id, :reason, :metadata, :created_at
                    )
                """
                ),
                {
                    "id": audit_log.id,
                    "profile_id": audit_log.profile_id,
                    "candidate_id": audit_log.candidate_id,
                    "action": audit_log.action.value,
                    "previous_status": audit_log.previous_status.value
                    if audit_log.previous_status
                    else None,
                    "new_status": audit_log.new_status.value
                    if audit_log.new_status
                    else None,
                    "actor_type": audit_log.actor_type,
                    "actor_id": audit_log.actor_id,
                    "reason": audit_log.reason,
                    "metadata": self.serialize_json(audit_log.metadata)
                    if audit_log.metadata
                    else None,
                    "created_at": audit_log.created_at,
                },
            )
            return audit_log

    def get_audit_logs(
        self,
        profile_id: str,
        candidate_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[HabitAuditLog]:
        """Get audit log entries."""
        query = "SELECT * FROM habit_audit_logs WHERE profile_id = :profile_id"
        params: Dict[str, Any] = {"profile_id": profile_id, "limit": limit}

        if candidate_id:
            query += " AND candidate_id = :candidate_id"
            params["candidate_id"] = candidate_id

        query += " ORDER BY created_at DESC LIMIT :limit"

        with self.get_connection() as conn:
            rows = conn.execute(text(query), params).fetchall()
            return [self._row_to_audit_log(row) for row in rows]

    def apply_confirmed_habits(self, profile: MindscapeProfile) -> MindscapeProfile:
        """
        Apply confirmed habits to profile preferences.
        Do not modify the original object; return a new profile instance.
        """
        confirmed_habits = self.get_confirmed_habits(profile.id)
        if not confirmed_habits:
            return profile

        preferences_dict = profile.preferences.dict() if profile.preferences else {}

        for habit in confirmed_habits:
            if habit.habit_category == HabitCategory.PREFERENCE:
                if habit.habit_key in [
                    "language",
                    "communication_style",
                    "response_length",
                    "timezone",
                ]:
                    preferences_dict[habit.habit_key] = habit.habit_value

        from backend.app.models.mindscape import UserPreferences

        updated_preferences = UserPreferences(**preferences_dict)

        profile_dict = profile.dict()
        profile_dict["preferences"] = updated_preferences
        return MindscapeProfile(**profile_dict)

    def _row_to_observation(self, row) -> HabitObservation:
        """Convert database row to HabitObservation."""
        def _coerce_datetime(value: Optional[datetime]) -> Optional[datetime]:
            if value is None:
                return None
            if isinstance(value, datetime):
                return value
            return self.from_isoformat(value)

        return HabitObservation(
            id=row.id,
            profile_id=row.profile_id,
            habit_key=row.habit_key,
            habit_value=row.habit_value,
            habit_category=HabitCategory(row.habit_category),
            source_type=row.source_type,
            source_id=row.source_id,
            source_context=self.deserialize_json(row.source_context, None),
            has_insight_signal=bool(row.has_insight_signal)
            if row.has_insight_signal is not None
            else False,
            insight_score=row.insight_score or 0.0,
            observed_at=_coerce_datetime(row.observed_at) or _utc_now(),
            created_at=_coerce_datetime(row.created_at) or _utc_now(),
        )

    def _row_to_candidate(self, row) -> HabitCandidate:
        """Convert database row to HabitCandidate."""
        def _coerce_datetime(value: Optional[datetime]) -> Optional[datetime]:
            if value is None:
                return None
            if isinstance(value, datetime):
                return value
            return self.from_isoformat(value)

        return HabitCandidate(
            id=row.id,
            profile_id=row.profile_id,
            habit_key=row.habit_key,
            habit_value=row.habit_value,
            habit_category=HabitCategory(row.habit_category),
            evidence_count=row.evidence_count or 0,
            confidence=row.confidence or 0.0,
            first_seen_at=_coerce_datetime(row.first_seen_at),
            last_seen_at=_coerce_datetime(row.last_seen_at),
            evidence_refs=self.deserialize_json(row.evidence_refs, []),
            status=HabitCandidateStatus(row.status),
            created_at=_coerce_datetime(row.created_at) or _utc_now(),
            updated_at=_coerce_datetime(row.updated_at) or _utc_now(),
        )

    def _row_to_audit_log(self, row) -> HabitAuditLog:
        """Convert database row to HabitAuditLog."""
        def _coerce_datetime(value: Optional[datetime]) -> Optional[datetime]:
            if value is None:
                return None
            if isinstance(value, datetime):
                return value
            return self.from_isoformat(value)

        return HabitAuditLog(
            id=row.id,
            profile_id=row.profile_id,
            candidate_id=row.candidate_id,
            action=HabitAuditAction(row.action),
            previous_status=HabitCandidateStatus(row.previous_status)
            if row.previous_status
            else None,
            new_status=HabitCandidateStatus(row.new_status) if row.new_status else None,
            actor_type=row.actor_type,
            actor_id=row.actor_id,
            reason=row.reason,
            metadata=self.deserialize_json(row.metadata, None),
            created_at=_coerce_datetime(row.created_at) or _utc_now(),
        )
