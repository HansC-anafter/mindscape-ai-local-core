"""
Habit Learning Models

Defines data models for habit observations, candidate habits, and audit records.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field


class HabitCategory(str, Enum):
    """Habit category"""
    PREFERENCE = "preference"  # Preference settings (language, tone, etc.)
    TOOL_USAGE = "tool_usage"  # Tool usage habits
    TIME_PATTERN = "time_pattern"  # Time patterns
    PLAYBOOK_USAGE = "playbook_usage"  # Playbook usage habits


class HabitCandidateStatus(str, Enum):
    """Candidate habit status"""
    PENDING = "pending"  # Pending confirmation
    CONFIRMED = "confirmed"  # Confirmed
    REJECTED = "rejected"  # Rejected
    SUPERSEDED = "superseded"  # Superseded


class HabitAuditAction(str, Enum):
    """Audit action type"""
    CREATED = "created"  # Created
    CONFIRMED = "confirmed"  # Confirmed
    REJECTED = "rejected"  # Rejected
    SUPERSEDED = "superseded"  # Superseded
    ROLLED_BACK = "rolled_back"  # Rolled back


class HabitObservation(BaseModel):
    """Habit observation record"""
    id: str = Field(..., description="Unique identifier")
    profile_id: str = Field(..., description="Associated profile ID")

    # Observation content
    habit_key: str = Field(..., description="Habit key (e.g., 'language', 'communication_style')")
    habit_value: str = Field(..., description="Observed value (e.g., 'zh-TW', 'casual')")
    habit_category: HabitCategory = Field(..., description="Habit category")

    # Source information
    source_type: str = Field(..., description="Source type ('agent_execution', 'playbook_execution', 'webhook', 'chat')")
    source_id: Optional[str] = Field(None, description="Source record ID (e.g., execution_id)")
    source_context: Optional[Dict[str, Any]] = Field(None, description="Additional context (JSON format)")

    # Insight signal (for flexible creative collection)
    has_insight_signal: bool = Field(default=False, description="Whether contains creative/insight signal")
    insight_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Insight score (0-1)")

    # Timestamps
    observed_at: datetime = Field(default_factory=datetime.utcnow, description="Observation time")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation time")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class HabitCandidate(BaseModel):
    """Candidate habit"""
    id: str = Field(..., description="Unique identifier")
    profile_id: str = Field(..., description="Associated profile ID")

    # Candidate habit
    habit_key: str = Field(..., description="Habit key")
    habit_value: str = Field(..., description="Habit value")
    habit_category: HabitCategory = Field(..., description="Habit category")

    # Statistics
    evidence_count: int = Field(default=0, description="Observation count")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence (0.0-1.0)")
    first_seen_at: Optional[datetime] = Field(None, description="First observation time")
    last_seen_at: Optional[datetime] = Field(None, description="Last observation time")

    # Evidence references
    evidence_refs: List[str] = Field(default_factory=list, description="Observation record ID list")

    # Status
    status: HabitCandidateStatus = Field(default=HabitCandidateStatus.PENDING, description="Status")

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation time")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Update time")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class HabitAuditLog(BaseModel):
    """Habit audit log"""
    id: str = Field(..., description="Unique identifier")
    profile_id: str = Field(..., description="Associated profile ID")
    candidate_id: str = Field(..., description="Associated candidate ID")

    # Change information
    action: HabitAuditAction = Field(..., description="Action type")
    previous_status: Optional[HabitCandidateStatus] = Field(None, description="Status before change")
    new_status: Optional[HabitCandidateStatus] = Field(None, description="Status after change")

    # Actor information
    actor_type: str = Field(default="system", description="Actor type ('system', 'user')")
    actor_id: Optional[str] = Field(None, description="Actor ID")

    # Reason/notes
    reason: Optional[str] = Field(None, description="Change reason")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional information (JSON format)")

    # Timestamp
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation time")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# API Request/Response models

class CreateHabitObservationRequest(BaseModel):
    """Request to create habit observation"""
    habit_key: str
    habit_value: str
    habit_category: HabitCategory
    source_type: str
    source_id: Optional[str] = None
    source_context: Optional[Dict[str, Any]] = None


class ConfirmHabitCandidateRequest(BaseModel):
    """Request to confirm candidate habit"""
    reason: Optional[str] = None


class RejectHabitCandidateRequest(BaseModel):
    """Request to reject candidate habit"""
    reason: Optional[str] = None


class HabitCandidateResponse(BaseModel):
    """Candidate habit response"""
    candidate: HabitCandidate
    suggestion_message: str = Field(..., description="Suggestion message (for UI display)")


class HabitMetricsResponse(BaseModel):
    """Habit learning statistics"""
    total_observations: int
    total_candidates: int
    pending_candidates: int
    confirmed_candidates: int
    rejected_candidates: int
    acceptance_rate: float = Field(ge=0.0, le=1.0, description="Acceptance rate (confirmed / (confirmed + rejected))")
    candidate_hit_rate: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Candidate hit rate (proportion of observations that generated candidates)"
    )
    is_habit_suggestions_enabled: Optional[bool] = Field(
        None,
        description="Whether habit suggestions feature is enabled"
    )
