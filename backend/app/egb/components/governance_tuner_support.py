"""Support types for the governance tuner facade."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from backend.app.egb.schemas.decision_record import DecisionRecord


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


@dataclass
class GovernanceSettings:
    """Current governance settings."""

    strictness_level: int = 0
    allowed_tools: List[str] = None
    denied_tools: List[str] = None
    scope_locked: bool = False
    verifier_enabled: bool = False
    consistency_mode: bool = False
    cost_limit_usd: float = 0.0

    def __post_init__(self):
        if self.allowed_tools is None:
            self.allowed_tools = []
        if self.denied_tools is None:
            self.denied_tools = []


@dataclass
class ApplyResult:
    """Result of applying a governance prescription."""

    success: bool
    applied_actions: List[str]
    failed_actions: List[str]
    decision_record: Optional[DecisionRecord] = None
    error: Optional[str] = None
