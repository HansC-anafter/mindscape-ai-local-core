"""
PhaseAttempt — tracks individual dispatch attempts for a PhaseIR.

Each time the DispatchOrchestrator dispatches a phase, a PhaseAttempt
record is created.  Attempts form the audit trail for retry, reroute,
and rollback decisions.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


def _utc_now() -> datetime:
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------
# Enums
# ------------------------------------------------------------------


class AttemptStatus(str, Enum):
    """Lifecycle states of a single dispatch attempt."""

    PENDING = "pending"  # Created, not yet dispatched
    DISPATCHED = "dispatched"  # Sent to adapter/engine
    RUNNING = "running"  # Adapter confirmed execution started
    COMPLETED = "completed"  # Successfully finished
    FAILED = "failed"  # Terminal failure for this attempt
    SKIPPED = "skipped"  # Skipped (upstream dependency failed)
    CANCELLED = "cancelled"  # Cancelled by supervisor or user


class DispatchEventKind(str, Enum):
    """Types of events recorded during dispatch lifecycle."""

    CREATED = "created"
    DISPATCHED = "dispatched"
    STARTED = "started"
    PROGRESS = "progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    RETRIED = "retried"
    REROUTED = "rerouted"


# ------------------------------------------------------------------
# Models
# ------------------------------------------------------------------


class DispatchEvent(BaseModel):
    """Single event in the PhaseAttempt lifecycle (append-only log)."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    attempt_id: str = Field(..., description="Parent PhaseAttempt ID")
    kind: DispatchEventKind = Field(..., description="Event type")
    timestamp: datetime = Field(default_factory=_utc_now)
    payload: Dict[str, Any] = Field(
        default_factory=dict, description="Event-specific data"
    )

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})


class PhaseAttempt(BaseModel):
    """Tracks a single dispatch attempt for a PhaseIR.

    Multiple attempts may exist for the same phase_id (retries).
    Only the latest attempt drives phase status.

    Invariants:
      - attempt_number is monotonically increasing per (task_ir_id, phase_id).
      - idempotency_key = f"{task_ir_id}:{phase_id}:{attempt_number}" to
        prevent duplicate dispatches.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_ir_id: str = Field(..., description="Parent TaskIR ID")
    phase_id: str = Field(..., description="PhaseIR.id being dispatched")

    attempt_number: int = Field(
        default=1, description="1-based attempt counter for this phase"
    )
    status: AttemptStatus = Field(default=AttemptStatus.PENDING)

    # Adapter selection
    engine: Optional[str] = Field(
        None, description="Engine/adapter used (e.g. 'playbook:generic')"
    )
    adapter_meta: Dict[str, Any] = Field(
        default_factory=dict,
        description="Adapter-specific metadata (execution_id, playbook_code, etc.)",
    )

    # Target
    target_workspace_id: Optional[str] = Field(
        None, description="Workspace this attempt dispatches into"
    )

    # Result
    result: Optional[Dict[str, Any]] = Field(
        None, description="Adapter result on completion"
    )
    error: Optional[str] = Field(None, description="Error message on failure")

    # Idempotency
    @property
    def idempotency_key(self) -> str:
        return f"{self.task_ir_id}:{self.phase_id}:{self.attempt_number}"

    # Timestamps
    created_at: datetime = Field(default_factory=_utc_now)
    dispatched_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Events (denormalized for convenience; canonical store is DispatchEvent)
    events: List[DispatchEvent] = Field(default_factory=list)

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------

    def mark_dispatched(self, engine: str, **adapter_meta: Any) -> DispatchEvent:
        """Transition PENDING → DISPATCHED."""
        self.status = AttemptStatus.DISPATCHED
        self.engine = engine
        self.adapter_meta.update(adapter_meta)
        self.dispatched_at = _utc_now()
        ev = DispatchEvent(
            attempt_id=self.id,
            kind=DispatchEventKind.DISPATCHED,
            payload={"engine": engine, **adapter_meta},
        )
        self.events.append(ev)
        return ev

    def mark_started(self) -> DispatchEvent:
        """Transition DISPATCHED → RUNNING."""
        self.status = AttemptStatus.RUNNING
        self.started_at = _utc_now()
        ev = DispatchEvent(attempt_id=self.id, kind=DispatchEventKind.STARTED)
        self.events.append(ev)
        return ev

    def mark_completed(self, result: Optional[Dict[str, Any]] = None) -> DispatchEvent:
        """Transition → COMPLETED (terminal)."""
        self.status = AttemptStatus.COMPLETED
        self.result = result
        self.completed_at = _utc_now()
        ev = DispatchEvent(
            attempt_id=self.id,
            kind=DispatchEventKind.COMPLETED,
            payload={"result_keys": list((result or {}).keys())},
        )
        self.events.append(ev)
        return ev

    def mark_failed(self, error: str) -> DispatchEvent:
        """Transition → FAILED (terminal for this attempt)."""
        self.status = AttemptStatus.FAILED
        self.error = error
        self.completed_at = _utc_now()
        ev = DispatchEvent(
            attempt_id=self.id,
            kind=DispatchEventKind.FAILED,
            payload={"error": error},
        )
        self.events.append(ev)
        return ev

    def mark_skipped(self, reason: str = "upstream_failed") -> DispatchEvent:
        """Transition → SKIPPED (dependency gate blocked)."""
        self.status = AttemptStatus.SKIPPED
        self.error = reason
        self.completed_at = _utc_now()
        ev = DispatchEvent(
            attempt_id=self.id,
            kind=DispatchEventKind.SKIPPED,
            payload={"reason": reason},
        )
        self.events.append(ev)
        return ev

    def mark_cancelled(self, reason: str = "cancelled") -> DispatchEvent:
        """Transition → CANCELLED."""
        self.status = AttemptStatus.CANCELLED
        self.error = reason
        self.completed_at = _utc_now()
        ev = DispatchEvent(
            attempt_id=self.id,
            kind=DispatchEventKind.CANCELLED,
            payload={"reason": reason},
        )
        self.events.append(ev)
        return ev

    @property
    def is_terminal(self) -> bool:
        """True if this attempt has reached a terminal state."""
        return self.status in (
            AttemptStatus.COMPLETED,
            AttemptStatus.FAILED,
            AttemptStatus.SKIPPED,
            AttemptStatus.CANCELLED,
        )
