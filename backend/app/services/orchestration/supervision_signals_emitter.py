"""
SupervisionSignalsEmitter — compute L5 → L3 signals from PhaseAttempt history.

Reads PhaseAttempt records and session state to produce a
SupervisionSignals snapshot that the DispatchGate (L3) uses
for gating decisions.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.models.phase_attempt import AttemptStatus, PhaseAttempt
from backend.app.models.supervision_signals import SupervisionSignals

logger = logging.getLogger(__name__)


class SupervisionSignalsEmitter:
    """Compute supervision signals from runtime state.

    Args:
        max_retries: Total retry budget per session.
        max_concurrent: Max concurrent dispatches.
        session_budget_s: Total session time budget (seconds).
        risk_decay_per_failure: How much risk budget each failure consumes.
    """

    def __init__(
        self,
        max_retries: int = 3,
        max_concurrent: int = 5,
        session_budget_s: float = 600.0,
        risk_decay_per_failure: float = 0.2,
    ):
        self.max_retries = max_retries
        self.max_concurrent = max_concurrent
        self.session_budget_s = session_budget_s
        self.risk_decay_per_failure = risk_decay_per_failure

    def compute(
        self,
        attempts: List[PhaseAttempt],
        session_start: Optional[datetime] = None,
        historical_stats: Optional[Dict[str, Any]] = None,
    ) -> SupervisionSignals:
        """Compute signals from current PhaseAttempt state.

        Args:
            attempts: All PhaseAttempts for the current session/TaskIR.
            session_start: When the session started (for age computation).
            historical_stats: Optional dict with 'failure_rate' and 'avg_time_s'.

        Returns:
            SupervisionSignals snapshot.
        """
        # Count states
        total_failures = sum(1 for a in attempts if a.status == AttemptStatus.FAILED)
        active = sum(
            1
            for a in attempts
            if a.status in (AttemptStatus.DISPATCHED, AttemptStatus.RUNNING)
        )
        total_retries_used = sum(max(0, a.attempt_number - 1) for a in attempts)

        # Risk budget: decays with each failure
        risk_remaining = max(0.0, 1.0 - (total_failures * self.risk_decay_per_failure))

        # Retry budget
        retry_remaining = max(0, self.max_retries - total_retries_used)

        # Session age
        session_age = 0.0
        if session_start:
            delta = datetime.now(timezone.utc) - session_start
            session_age = max(0.0, delta.total_seconds())

        # Historical intelligence
        stats = historical_stats or {}
        failure_rate = stats.get("failure_rate", 0.0)
        avg_time = stats.get("avg_time_s", None)

        return SupervisionSignals(
            risk_budget_remaining=round(risk_remaining, 3),
            retry_budget_remaining=retry_remaining,
            historical_failure_rate=failure_rate,
            avg_execution_time_s=avg_time,
            active_dispatches=active,
            max_concurrent_dispatches=self.max_concurrent,
            session_age_s=round(session_age, 1),
            session_budget_s=self.session_budget_s,
        )
