"""Suggestion and candidate conflict helpers for habit routes."""

import uuid
from datetime import datetime

from backend.app.models.habit import HabitCandidate, HabitCandidateStatus
from backend.features.habits.dependencies import habit_store


def _generate_suggestion_message(candidate: HabitCandidate) -> str:
    """Generate suggestion message"""
    habit_key_display = {
        "language": "語言",
        "communication_style": "溝通風格",
        "response_length": "回應長度",
        "executor_runtime_type": "Preferred agent type",
        "tool_usage": "工具使用",
        "playbook_usage": "Playbook 使用",
    }.get(candidate.habit_key, candidate.habit_key)

    confidence_percentage = int(candidate.confidence * 100)
    evidence_count = candidate.evidence_count

    return (
        f"偵測到你常用「{candidate.habit_value}」作為 {habit_key_display}。"
        f"在最近 {evidence_count} 次使用中，這個偏好出現了 {confidence_percentage}% 的機率。"
        f"要設為預設嗎？"
    )


def _supersede_conflicting_candidates(
    profile_id: str, confirmed_candidate: HabitCandidate
) -> None:
    """
    Mark other confirmed candidates with the same key as superseded

    Args:
        profile_id: Profile ID
        confirmed_candidate: The candidate that was just confirmed
    """
    try:
        all_candidates = habit_store.get_candidates(profile_id=profile_id, limit=10000)
        conflicting = [
            c
            for c in all_candidates
            if (
                c.habit_key == confirmed_candidate.habit_key
                and c.id != confirmed_candidate.id
                and c.status == HabitCandidateStatus.CONFIRMED
            )
        ]

        for candidate in conflicting:
            previous_status = candidate.status
            candidate.status = HabitCandidateStatus.SUPERSEDED
            candidate.updated_at = datetime.utcnow()
            habit_store.update_candidate(candidate)

            from backend.app.models.habit import HabitAuditAction, HabitAuditLog

            audit_log = HabitAuditLog(
                id=str(uuid.uuid4()),
                profile_id=profile_id,
                candidate_id=candidate.id,
                action=HabitAuditAction.SUPERSEDED,
                previous_status=previous_status,
                new_status=HabitCandidateStatus.SUPERSEDED,
                actor_type="system",
                reason=f"Superseded by candidate {confirmed_candidate.id}",
                created_at=datetime.utcnow(),
            )
            habit_store.create_audit_log(audit_log)

    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to supersede conflicting candidates: {e}")
