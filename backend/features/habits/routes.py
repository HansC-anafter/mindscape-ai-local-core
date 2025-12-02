"""
Habit Learning API routes

Handles habit candidate confirmation, rejection, querying, and audit logging.
"""

import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel

from backend.app.models.habit import (
    HabitCandidate,
    HabitCandidateResponse,
    HabitAuditLog,
    HabitMetricsResponse,
    ConfirmHabitCandidateRequest,
    RejectHabitCandidateRequest,
    HabitCandidateStatus,
)
from backend.app.services.habit_store import HabitStore
from backend.app.services.mindscape_store import MindscapeStore

router = APIRouter(tags=["habits"])

# Initialize stores
habit_store = HabitStore()
mindscape_store = MindscapeStore()


@router.get("/candidates", response_model=List[HabitCandidateResponse])
async def get_candidates(
    profile_id: str = Query(..., description="Profile ID"),
    status: Optional[str] = Query(None, description="Filter by status (pending, confirmed, rejected)"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of candidates to return")
):
    """
    Get list of habit candidates

    Args:
        profile_id: Profile ID
        status: Filter by status (optional)
        limit: Maximum number of results to return
    """
    try:
        # Parse status filter
        status_filter = None
        if status:
            try:
                status_filter = HabitCandidateStatus(status.lower())
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status: {status}. Must be one of: pending, confirmed, rejected, superseded"
                )

        # Get candidate list
        candidates = habit_store.get_candidates(
            profile_id=profile_id,
            status=status_filter,
            limit=limit
        )

        # Convert to response format
        responses = []
        for candidate in candidates:
            # Generate suggestion message
            suggestion_message = _generate_suggestion_message(candidate)

            responses.append(HabitCandidateResponse(
                candidate=candidate,
                suggestion_message=suggestion_message
            ))

        return responses

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get candidates: {str(e)}")


@router.get("/candidates/{candidate_id}", response_model=HabitCandidate)
async def get_candidate(
    candidate_id: str = Path(..., description="Candidate ID"),
    profile_id: str = Query(..., description="Profile ID")
):
    """Get a single habit candidate"""
    try:
        # Get all candidates, then filter
        candidates = habit_store.get_candidates(profile_id=profile_id, limit=1000)
        candidate = next((c for c in candidates if c.id == candidate_id), None)

        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")

        return candidate

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get candidate: {str(e)}")


@router.post("/candidates/{candidate_id}/confirm", response_model=HabitCandidate)
async def confirm_candidate(
    candidate_id: str = Path(..., description="Candidate ID"),
    profile_id: str = Query(..., description="Profile ID"),
    request: Optional[ConfirmHabitCandidateRequest] = None
):
    """
    Confirm a habit candidate

    Changes candidate status from pending to confirmed and creates audit log.
    """
    try:
        # Get candidate
        candidates = habit_store.get_candidates(profile_id=profile_id, limit=1000)
        candidate = next((c for c in candidates if c.id == candidate_id), None)

        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")

        if candidate.status == HabitCandidateStatus.CONFIRMED:
            # Already confirmed, return directly
            return candidate

        if candidate.status == HabitCandidateStatus.REJECTED:
            raise HTTPException(
                status_code=400,
                detail="Cannot confirm a rejected candidate. Please create a new candidate or use rollback."
            )

        # Record previous status
        previous_status = candidate.status

        # Update status
        candidate.status = HabitCandidateStatus.CONFIRMED
        candidate.updated_at = datetime.utcnow()

        # If there are other confirmed candidates with the same key, mark them as superseded
        _supersede_conflicting_candidates(profile_id, candidate)

        # Save update
        habit_store.update_candidate(candidate)

        # Create audit log
        from backend.app.models.habit import HabitAuditLog, HabitAuditAction
        audit_log = HabitAuditLog(
            id=str(uuid.uuid4()),
            profile_id=profile_id,
            candidate_id=candidate_id,
            action=HabitAuditAction.CONFIRMED,
            previous_status=previous_status,
            new_status=HabitCandidateStatus.CONFIRMED,
            actor_type="user",
            actor_id=profile_id,
            reason=request.reason if request else None,
            created_at=datetime.utcnow()
        )
        habit_store.create_audit_log(audit_log)

        return candidate

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to confirm candidate: {str(e)}")


@router.post("/candidates/{candidate_id}/reject", response_model=HabitCandidate)
async def reject_candidate(
    candidate_id: str = Path(..., description="Candidate ID"),
    profile_id: str = Query(..., description="Profile ID"),
    request: Optional[RejectHabitCandidateRequest] = None
):
    """
    Reject a habit candidate

    Changes candidate status from pending to rejected and creates audit log.
    """
    try:
        # Get candidate
        candidates = habit_store.get_candidates(profile_id=profile_id, limit=1000)
        candidate = next((c for c in candidates if c.id == candidate_id), None)

        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")

        if candidate.status == HabitCandidateStatus.REJECTED:
            # Already rejected, return directly
            return candidate

        # Record previous status
        previous_status = candidate.status

        # Update status
        candidate.status = HabitCandidateStatus.REJECTED
        candidate.updated_at = datetime.utcnow()

        # Save update
        habit_store.update_candidate(candidate)

        # Create audit log
        from backend.app.models.habit import HabitAuditLog, HabitAuditAction
        audit_log = HabitAuditLog(
            id=str(uuid.uuid4()),
            profile_id=profile_id,
            candidate_id=candidate_id,
            action=HabitAuditAction.REJECTED,
            previous_status=previous_status,
            new_status=HabitCandidateStatus.REJECTED,
            actor_type="user",
            actor_id=profile_id,
            reason=request.reason if request else None,
            created_at=datetime.utcnow()
        )
        habit_store.create_audit_log(audit_log)

        return candidate

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reject candidate: {str(e)}")


@router.post("/candidates/{candidate_id}/rollback", response_model=HabitCandidate)
async def rollback_candidate(
    candidate_id: str = Path(..., description="Candidate ID"),
    profile_id: str = Query(..., description="Profile ID")
):
    """
    Rollback a habit candidate to previous status

    Finds previous status from audit logs, restores candidate and creates new audit log.
    """
    try:
        # Get candidate
        candidates = habit_store.get_candidates(profile_id=profile_id, limit=1000)
        candidate = next((c for c in candidates if c.id == candidate_id), None)

        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")

        # Get audit logs (sorted by time descending)
        audit_logs = habit_store.get_audit_logs(
            profile_id=profile_id,
            candidate_id=candidate_id,
            limit=100
        )

        if not audit_logs:
            raise HTTPException(
                status_code=400,
                detail="No audit logs found for this candidate. Cannot rollback."
            )

        # Find the last non-rollback audit log
        last_meaningful_log = None
        for log in audit_logs:
            if log.action.value != "rolled_back":
                last_meaningful_log = log
                break

        if not last_meaningful_log:
            raise HTTPException(
                status_code=400,
                detail="No meaningful audit log found. Cannot rollback."
            )

        # Determine target status for rollback
        # If current is confirmed, rollback to previous status (may be pending)
        # If current is rejected, rollback to previous status (may be pending or confirmed)
        target_status = last_meaningful_log.previous_status

        if not target_status:
            raise HTTPException(
                status_code=400,
                detail="Cannot determine target status for rollback."
            )

        # Record current status
        current_status = candidate.status

        # Update status
        candidate.status = target_status
        candidate.updated_at = datetime.utcnow()

        # Save update
        habit_store.update_candidate(candidate)

        # Create audit log
        from backend.app.models.habit import HabitAuditLog, HabitAuditAction
        audit_log = HabitAuditLog(
            id=str(uuid.uuid4()),
            profile_id=profile_id,
            candidate_id=candidate_id,
            action=HabitAuditAction.ROLLED_BACK,
            previous_status=current_status,
            new_status=target_status,
            actor_type="user",
            actor_id=profile_id,
            reason=f"Rolled back from {current_status.value} to {target_status.value}",
            metadata={
                "rolled_back_from": current_status.value,
                "rolled_back_to": target_status.value,
                "reference_audit_log_id": last_meaningful_log.id
            },
            created_at=datetime.utcnow()
        )
        habit_store.create_audit_log(audit_log)

        return candidate

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to rollback candidate: {str(e)}")


@router.get("/audit-logs", response_model=List[HabitAuditLog])
async def get_audit_logs(
    profile_id: str = Query(..., description="Profile ID"),
    candidate_id: Optional[str] = Query(None, description="Filter by candidate ID"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of logs to return")
):
    """Get audit logs"""
    try:
        logs = habit_store.get_audit_logs(
            profile_id=profile_id,
            candidate_id=candidate_id,
            limit=limit
        )
        return logs

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get audit logs: {str(e)}")


@router.get("/metrics", response_model=HabitMetricsResponse)
async def get_metrics(
    profile_id: str = Query(..., description="Profile ID")
):
    """
    Get habit learning statistics

    Includes:
    - Total observation count
    - Candidate statistics (total, pending, confirmed, rejected)
    - Acceptance rate (confirmed / (confirmed + rejected))
    """
    try:
        # Get all candidates
        all_candidates = habit_store.get_candidates(profile_id=profile_id, limit=10000)

        # Calculate statistics
        total_candidates = len(all_candidates)
        pending_candidates = sum(1 for c in all_candidates if c.status == HabitCandidateStatus.PENDING)
        confirmed_candidates = sum(1 for c in all_candidates if c.status == HabitCandidateStatus.CONFIRMED)
        rejected_candidates = sum(1 for c in all_candidates if c.status == HabitCandidateStatus.REJECTED)
        superseded_candidates = sum(1 for c in all_candidates if c.status == HabitCandidateStatus.SUPERSEDED)

        # Calculate acceptance rate
        total_decisions = confirmed_candidates + rejected_candidates
        acceptance_rate = (confirmed_candidates / total_decisions) if total_decisions > 0 else 0.0

        # Get total observation count
        observations = habit_store.get_observations(profile_id=profile_id, limit=10000)
        total_observations = len(observations)

        # Calculate candidate hit rate (proportion of observations with candidates)
        # This is a simplified calculation: proportion of observations that generated candidates
        observations_with_candidates = set()
        for candidate in all_candidates:
            observations_with_candidates.update(candidate.evidence_refs[:10])  # Check at most first 10 evidence

        candidate_hit_rate = (len(observations_with_candidates) / total_observations) if total_observations > 0 else 0.0

        # Check if habit suggestions feature is enabled
        is_enabled = None
        try:
            profile = mindscape_store.get_profile(profile_id, apply_habits=False)
            if profile and profile.preferences:
                is_enabled = getattr(profile.preferences, 'enable_habit_suggestions', False)
        except Exception:
            pass  # If unable to get profile, set to None

        return HabitMetricsResponse(
            total_observations=total_observations,
            total_candidates=total_candidates,
            pending_candidates=pending_candidates,
            confirmed_candidates=confirmed_candidates,
            rejected_candidates=rejected_candidates,
            acceptance_rate=acceptance_rate,
            candidate_hit_rate=candidate_hit_rate,
            is_habit_suggestions_enabled=is_enabled
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get metrics: {str(e)}")


# Helper functions

def _generate_suggestion_message(candidate: HabitCandidate) -> str:
    """Generate suggestion message"""
    habit_key_display = {
        "language": "語言",
        "communication_style": "溝通風格",
        "response_length": "回應長度",
        "preferred_agent_type": "偏好的 Agent 類型",
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


def _supersede_conflicting_candidates(profile_id: str, confirmed_candidate: HabitCandidate):
    """
    Mark other confirmed candidates with the same key as superseded

    Args:
        profile_id: Profile ID
        confirmed_candidate: The candidate that was just confirmed
    """
    try:
        # Get all confirmed candidates with the same key
        all_candidates = habit_store.get_candidates(profile_id=profile_id, limit=10000)
        conflicting = [
            c for c in all_candidates
            if (c.habit_key == confirmed_candidate.habit_key and
                c.id != confirmed_candidate.id and
                c.status == HabitCandidateStatus.CONFIRMED)
        ]

        # Mark them as superseded
        for candidate in conflicting:
            previous_status = candidate.status
            candidate.status = HabitCandidateStatus.SUPERSEDED
            candidate.updated_at = datetime.utcnow()
            habit_store.update_candidate(candidate)

            # Create audit log
            from backend.app.models.habit import HabitAuditLog, HabitAuditAction
            audit_log = HabitAuditLog(
                id=str(uuid.uuid4()),
                profile_id=profile_id,
                candidate_id=candidate.id,
                action=HabitAuditAction.SUPERSEDED,
                previous_status=previous_status,
                new_status=HabitCandidateStatus.SUPERSEDED,
                actor_type="system",
                reason=f"Superseded by candidate {confirmed_candidate.id}",
                created_at=datetime.utcnow()
            )
            habit_store.create_audit_log(audit_log)

    except Exception as e:
        # Log error but don't interrupt confirmation flow
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to supersede conflicting candidates: {e}")
