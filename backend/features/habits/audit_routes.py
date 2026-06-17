"""Habit audit log route handlers."""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from backend.app.models.habit import HabitAuditLog
from backend.features.habits.dependencies import habit_store

router = APIRouter()


@router.get("/audit-logs", response_model=List[HabitAuditLog])
async def get_audit_logs(
    profile_id: str = Query(..., description="Profile ID"),
    candidate_id: Optional[str] = Query(None, description="Filter by candidate ID"),
    limit: int = Query(
        100, ge=1, le=500, description="Maximum number of logs to return"
    ),
) -> List[HabitAuditLog]:
    """Get audit logs"""
    try:
        logs = habit_store.get_audit_logs(
            profile_id=profile_id, candidate_id=candidate_id, limit=limit
        )
        return logs

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get audit logs: {str(e)}"
        )
