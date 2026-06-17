"""Habit candidate route handlers."""

import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Path, Query

from backend.app.models.habit import (
    ConfirmHabitCandidateRequest,
    HabitCandidate,
    HabitCandidateResponse,
    HabitCandidateStatus,
    RejectHabitCandidateRequest,
)
from backend.features.habits.dependencies import habit_store
from backend.features.habits.suggestion_helpers import (
    _generate_suggestion_message,
    _supersede_conflicting_candidates,
)

router = APIRouter()


@router.get("/candidates", response_model=List[HabitCandidateResponse])
async def get_candidates(
    profile_id: str = Query(..., description="Profile ID"),
    status: Optional[str] = Query(
        None, description="Filter by status (pending, confirmed, rejected)"
    ),
    limit: int = Query(
        50, ge=1, le=100, description="Maximum number of candidates to return"
    ),
) -> List[HabitCandidateResponse]:
    """
    Get list of habit candidates

    Args:
        profile_id: Profile ID
        status: Filter by status (optional)
        limit: Maximum number of results to return
    """
    try:
        status_filter = None
        if status:
            try:
                status_filter = HabitCandidateStatus(status.lower())
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status: {status}. Must be one of: pending, confirmed, rejected, superseded",
                )

        candidates = habit_store.get_candidates(
            profile_id=profile_id, status=status_filter, limit=limit
        )

        responses = []
        for candidate in candidates:
            suggestion_message = _generate_suggestion_message(candidate)
            responses.append(
                HabitCandidateResponse(
                    candidate=candidate, suggestion_message=suggestion_message
                )
            )

        return responses

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get candidates: {str(e)}"
        )


@router.get("/candidates/{candidate_id}", response_model=HabitCandidate)
async def get_candidate(
    candidate_id: str = Path(..., description="Candidate ID"),
    profile_id: str = Query(..., description="Profile ID"),
) -> HabitCandidate:
    """Get a single habit candidate"""
    try:
        candidates = habit_store.get_candidates(profile_id=profile_id, limit=1000)
        candidate = next((c for c in candidates if c.id == candidate_id), None)

        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")

        return candidate

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get candidate: {str(e)}"
        )


@router.post("/candidates/{candidate_id}/confirm", response_model=HabitCandidate)
async def confirm_candidate(
    candidate_id: str = Path(..., description="Candidate ID"),
    profile_id: str = Query(..., description="Profile ID"),
    request: Optional[ConfirmHabitCandidateRequest] = None,
) -> HabitCandidate:
    """
    Confirm a habit candidate

    Changes candidate status from pending to confirmed and creates audit log.
    """
    try:
        candidates = habit_store.get_candidates(profile_id=profile_id, limit=1000)
        candidate = next((c for c in candidates if c.id == candidate_id), None)

        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")

        if candidate.status == HabitCandidateStatus.CONFIRMED:
            return candidate

        if candidate.status == HabitCandidateStatus.REJECTED:
            raise HTTPException(
                status_code=400,
                detail="Cannot confirm a rejected candidate. Please create a new candidate or use rollback.",
            )

        previous_status = candidate.status
        candidate.status = HabitCandidateStatus.CONFIRMED
        candidate.updated_at = datetime.utcnow()

        _supersede_conflicting_candidates(profile_id, candidate)
        habit_store.update_candidate(candidate)

        from backend.app.models.habit import HabitAuditAction, HabitAuditLog

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
            created_at=datetime.utcnow(),
        )
        habit_store.create_audit_log(audit_log)

        return candidate

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to confirm candidate: {str(e)}"
        )


@router.post("/candidates/{candidate_id}/reject", response_model=HabitCandidate)
async def reject_candidate(
    candidate_id: str = Path(..., description="Candidate ID"),
    profile_id: str = Query(..., description="Profile ID"),
    request: Optional[RejectHabitCandidateRequest] = None,
) -> HabitCandidate:
    """
    Reject a habit candidate

    Changes candidate status from pending to rejected and creates audit log.
    """
    try:
        candidates = habit_store.get_candidates(profile_id=profile_id, limit=1000)
        candidate = next((c for c in candidates if c.id == candidate_id), None)

        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")

        if candidate.status == HabitCandidateStatus.REJECTED:
            return candidate

        previous_status = candidate.status
        candidate.status = HabitCandidateStatus.REJECTED
        candidate.updated_at = datetime.utcnow()

        habit_store.update_candidate(candidate)

        from backend.app.models.habit import HabitAuditAction, HabitAuditLog

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
            created_at=datetime.utcnow(),
        )
        habit_store.create_audit_log(audit_log)

        return candidate

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to reject candidate: {str(e)}"
        )


@router.post("/candidates/{candidate_id}/rollback", response_model=HabitCandidate)
async def rollback_candidate(
    candidate_id: str = Path(..., description="Candidate ID"),
    profile_id: str = Query(..., description="Profile ID"),
) -> HabitCandidate:
    """
    Rollback a habit candidate to previous status

    Finds previous status from audit logs, restores candidate and creates new audit log.
    """
    try:
        candidates = habit_store.get_candidates(profile_id=profile_id, limit=1000)
        candidate = next((c for c in candidates if c.id == candidate_id), None)

        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")

        audit_logs = habit_store.get_audit_logs(
            profile_id=profile_id, candidate_id=candidate_id, limit=100
        )

        if not audit_logs:
            raise HTTPException(
                status_code=400,
                detail="No audit logs found for this candidate. Cannot rollback.",
            )

        last_meaningful_log = None
        for log in audit_logs:
            if log.action.value != "rolled_back":
                last_meaningful_log = log
                break

        if not last_meaningful_log:
            raise HTTPException(
                status_code=400,
                detail="No meaningful audit log found. Cannot rollback.",
            )

        target_status = last_meaningful_log.previous_status

        if not target_status:
            raise HTTPException(
                status_code=400, detail="Cannot determine target status for rollback."
            )

        current_status = candidate.status
        candidate.status = target_status
        candidate.updated_at = datetime.utcnow()

        habit_store.update_candidate(candidate)

        from backend.app.models.habit import HabitAuditAction, HabitAuditLog

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
                "reference_audit_log_id": last_meaningful_log.id,
            },
            created_at=datetime.utcnow(),
        )
        habit_store.create_audit_log(audit_log)

        return candidate

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to rollback candidate: {str(e)}"
        )
