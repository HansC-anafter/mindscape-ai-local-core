"""
Lens Metrics models for Mind-Lens result indicators.

Provides models for tracking and analyzing lens effectiveness:
- Preview votes (user choice: base vs lens)
- Convergence metrics (rerun count, edit count, time to accept)
- Apply target tracking (session/workspace/preset)
- Coverage metrics (emphasized nodes trigger rate)
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime, timezone
from enum import Enum


class ChosenVariant(str, Enum):
    """User's chosen variant"""
    BASE = "base"
    LENS = "lens"


class ApplyTarget(str, Enum):
    """Where the changes were applied"""
    SESSION_ONLY = "session_only"
    WORKSPACE = "workspace"
    PRESET = "preset"


class PreviewVote(BaseModel):
    """User's vote on preview output"""
    id: str
    preview_id: str  # Links to preview session/execution
    workspace_id: str
    profile_id: str
    session_id: Optional[str] = None
    chosen_variant: ChosenVariant
    preview_type: Optional[str] = None
    input_text_hash: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class PreviewVoteCreateRequest(BaseModel):
    """Request to create a preview vote"""
    preview_id: str
    workspace_id: str
    profile_id: str
    session_id: Optional[str] = None
    chosen_variant: ChosenVariant
    preview_type: Optional[str] = None
    input_text: Optional[str] = None  # Will be hashed if provided


class ConvergenceMetrics(BaseModel):
    """Metrics for task convergence"""
    average_rerun_count: float
    average_edit_count: float
    average_time_to_accept_ms: float
    total_tasks: int
    accepted_tasks: int
    acceptance_rate: float


class SelectionMetrics(BaseModel):
    """Metrics for user selection behavior"""
    total_votes: int
    base_votes: int
    lens_votes: int
    lens_selection_rate: float  # Percentage of times lens was chosen


class ApplyTargetMetrics(BaseModel):
    """Metrics for apply target distribution"""
    session_only_count: int
    workspace_count: int
    preset_count: int
    total_applies: int
    workspace_promotion_rate: float  # Percentage promoted to workspace
    preset_promotion_rate: float  # Percentage promoted to preset


class CoverageMetrics(BaseModel):
    """Metrics for node coverage"""
    total_emphasized_nodes: int
    triggered_emphasized_nodes: int
    coverage_rate: float  # Percentage of emphasized nodes that were triggered


class MetricsReport(BaseModel):
    """Comprehensive metrics report"""
    workspace_id: str
    profile_id: Optional[str] = None
    time_range_start: Optional[datetime] = None
    time_range_end: Optional[datetime] = None

    # Core metrics
    selection_metrics: SelectionMetrics
    convergence_metrics: Optional[ConvergenceMetrics] = None
    apply_target_metrics: Optional[ApplyTargetMetrics] = None
    coverage_metrics: Optional[CoverageMetrics] = None

    # Additional insights
    lens_effectiveness_score: Optional[float] = None  # Composite score 0-1
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class MetricsQuery(BaseModel):
    """Query parameters for metrics"""
    workspace_id: str
    profile_id: Optional[str] = None
    session_id: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    include_convergence: bool = True
    include_apply_target: bool = True
    include_coverage: bool = True

