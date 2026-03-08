"""
Supervision Signals — typed L5 → L3 signals.

These signals carry runtime intelligence from L5 (RuntimeSupervisor)
down to L3 (DispatchGate) to influence dispatch decisions.

Until Phase 4 (L5 RuntimeSupervisor) is implemented, these are
populated with safe defaults and can be overridden in tests.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SupervisionSignals(BaseModel):
    """Signals from L5 supervision layer to L3 dispatch gate.

    All fields have safe defaults so the system works without
    an active L5 supervisor (Phase 4 dependency).
    """

    # Risk management
    risk_budget_remaining: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Fraction of risk budget remaining (1.0 = full budget, 0.0 = exhausted)",
    )

    # Retry management
    retry_budget_remaining: int = Field(
        default=3,
        ge=0,
        description="Number of retries remaining for this session",
    )

    # Historical intelligence
    historical_failure_rate: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Historical failure rate for this playbook/tool (0.0-1.0)",
    )
    avg_execution_time_s: Optional[float] = Field(
        default=None,
        description="Average execution time in seconds (None = unknown)",
    )

    # Concurrency
    active_dispatches: int = Field(
        default=0,
        ge=0,
        description="Number of currently active dispatches in this session",
    )
    max_concurrent_dispatches: int = Field(
        default=5,
        ge=1,
        description="Maximum concurrent dispatches allowed",
    )

    # Session state
    session_age_s: float = Field(
        default=0.0,
        ge=0.0,
        description="Session age in seconds",
    )
    session_budget_s: float = Field(
        default=600.0,
        description="Total session time budget in seconds",
    )

    # Custom signals from L5 plugins
    custom: Dict[str, Any] = Field(
        default_factory=dict,
        description="Extension point for custom L5 signals",
    )

    @property
    def risk_budget_exhausted(self) -> bool:
        """True if risk budget is fully consumed."""
        return self.risk_budget_remaining <= 0.0

    @property
    def concurrency_at_limit(self) -> bool:
        """True if concurrent dispatch limit is reached."""
        return self.active_dispatches >= self.max_concurrent_dispatches

    @property
    def session_time_remaining_s(self) -> float:
        """Remaining session time in seconds."""
        return max(0.0, self.session_budget_s - self.session_age_s)
