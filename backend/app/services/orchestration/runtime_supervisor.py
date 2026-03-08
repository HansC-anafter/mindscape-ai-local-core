"""
RuntimeSupervisor — runtime observation and recovery for dispatch phases.

Upgrades MeetingSupervisor from post-mortem-only to runtime controller.
Detects stuck/failed phases and emits recovery actions (retry, cancel, reroute).

The observation loop is designed to run as a background task, never blocking
the main meeting flow.

Recovery actions:
  - RETRY:   Re-dispatch the same phase (increment attempt_number)
  - CANCEL:  Mark PhaseAttempt as CANCELLED
  - REROUTE: Switch adapter (e.g. playbook → tool_execution)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from backend.app.models.phase_attempt import AttemptStatus, PhaseAttempt
from backend.app.models.supervision_signals import SupervisionSignals
from backend.app.services.orchestration.supervision_signals_emitter import (
    SupervisionSignalsEmitter,
)

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Recovery action types
# ------------------------------------------------------------------


class RecoveryAction(str, Enum):
    """Actions the supervisor can emit for stuck/failed phases."""

    RETRY = "retry"
    CANCEL = "cancel"
    REROUTE = "reroute"
    NOOP = "noop"


class RecoveryDirective(BaseModel):
    """A single recovery instruction for a phase."""

    phase_id: str
    attempt_id: str
    action: RecoveryAction
    reason: str = ""
    reroute_engine: Optional[str] = Field(
        None, description="Target engine for REROUTE actions"
    )


# ------------------------------------------------------------------
# RuntimeSupervisor
# ------------------------------------------------------------------


class RuntimeSupervisor:
    """Runtime observation and recovery controller.

    Designed to be instantiated per-session. Call `observe()` periodically
    (or once after dispatch) to detect stuck phases and emit recovery actions.

    Args:
        stuck_threshold_s: Seconds without progress to consider a phase stuck.
        max_retries_per_phase: Max retries before escalating to CANCEL.
        emitter: Optional SupervisionSignalsEmitter for signal computation.
    """

    def __init__(
        self,
        stuck_threshold_s: float = 300.0,
        max_retries_per_phase: int = 2,
        emitter: Optional[SupervisionSignalsEmitter] = None,
    ):
        self.stuck_threshold_s = stuck_threshold_s
        self.max_retries_per_phase = max_retries_per_phase
        self.emitter = emitter or SupervisionSignalsEmitter()

    # ------------------------------------------------------------------
    # Observation
    # ------------------------------------------------------------------

    def observe(
        self,
        attempts: List[PhaseAttempt],
        now: Optional[datetime] = None,
    ) -> List[RecoveryDirective]:
        """Observe current PhaseAttempts and emit recovery directives.

        Args:
            attempts: All attempts for the current TaskIR.
            now: Current timestamp (injectable for testing).

        Returns:
            List of recovery directives for phases needing attention.
        """
        now = now or datetime.now(timezone.utc)
        directives: List[RecoveryDirective] = []

        for attempt in attempts:
            directive = self._evaluate_attempt(attempt, now)
            if directive and directive.action != RecoveryAction.NOOP:
                directives.append(directive)

        return directives

    def _evaluate_attempt(
        self,
        attempt: PhaseAttempt,
        now: datetime,
    ) -> Optional[RecoveryDirective]:
        """Evaluate a single attempt for recovery needs."""

        # Only evaluate non-terminal attempts
        if attempt.is_terminal:
            # Check if FAILED → should retry?
            if attempt.status == AttemptStatus.FAILED:
                return self._handle_failed(attempt)
            return None

        # Check for stuck (dispatched/running but no progress)
        if attempt.status in (AttemptStatus.DISPATCHED, AttemptStatus.RUNNING):
            return self._check_stuck(attempt, now)

        return None

    def _check_stuck(
        self,
        attempt: PhaseAttempt,
        now: datetime,
    ) -> Optional[RecoveryDirective]:
        """Check if a dispatched/running attempt is stuck."""
        reference_time = (
            attempt.started_at or attempt.dispatched_at or attempt.created_at
        )
        elapsed = (now - reference_time).total_seconds()

        if elapsed > self.stuck_threshold_s:
            # Stuck → decide recovery action
            if attempt.attempt_number < self.max_retries_per_phase:
                return RecoveryDirective(
                    phase_id=attempt.phase_id,
                    attempt_id=attempt.id,
                    action=RecoveryAction.RETRY,
                    reason=f"stuck_{int(elapsed)}s",
                )
            else:
                return RecoveryDirective(
                    phase_id=attempt.phase_id,
                    attempt_id=attempt.id,
                    action=RecoveryAction.CANCEL,
                    reason=f"stuck_{int(elapsed)}s_max_retries_exhausted",
                )

        return None

    def _handle_failed(
        self,
        attempt: PhaseAttempt,
    ) -> Optional[RecoveryDirective]:
        """Decide recovery action for a failed attempt."""
        if attempt.attempt_number < self.max_retries_per_phase:
            return RecoveryDirective(
                phase_id=attempt.phase_id,
                attempt_id=attempt.id,
                action=RecoveryAction.RETRY,
                reason=f"failed:{attempt.error or 'unknown'}",
            )

        # Max retries exhausted → try reroute if playbook, else cancel
        engine = attempt.engine or ""
        if engine.startswith("playbook:"):
            return RecoveryDirective(
                phase_id=attempt.phase_id,
                attempt_id=attempt.id,
                action=RecoveryAction.REROUTE,
                reason="max_retries_exhausted_rerouting",
                reroute_engine="playbook:generic",
            )

        return RecoveryDirective(
            phase_id=attempt.phase_id,
            attempt_id=attempt.id,
            action=RecoveryAction.CANCEL,
            reason="max_retries_exhausted",
        )

    # ------------------------------------------------------------------
    # Signal emission
    # ------------------------------------------------------------------

    def compute_signals(
        self,
        attempts: List[PhaseAttempt],
        session_start: Optional[datetime] = None,
    ) -> SupervisionSignals:
        """Compute current supervision signals from attempt state.

        Delegates to SupervisionSignalsEmitter.
        """
        return self.emitter.compute(
            attempts=attempts,
            session_start=session_start,
        )
