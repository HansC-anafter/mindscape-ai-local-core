"""
Meeting session model for intent governance.

Represents a bounded governance meeting session with:
- Start/end timestamps
- State snapshots (before/after)
- Links to decisions, traces, and intent patches made during the session

Lifecycle triggers (planned):
- MEETING_START: First user message on a thread (or after idle timeout)
- MEETING_END: Explicit API call or idle timeout
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class MeetingStatus(str, Enum):
    """Lifecycle status for a governance meeting session."""

    PLANNED = "planned"
    ACTIVE = "active"
    CLOSING = "closing"
    CLOSED = "closed"
    ABORTED = "aborted"
    FAILED = "failed"


@dataclass
class MeetingSession:
    """A bounded governance meeting session."""

    id: str
    workspace_id: str
    project_id: Optional[str] = None
    thread_id: Optional[str] = None
    lens_id: Optional[str] = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: Optional[datetime] = None

    # State snapshots for diff computation
    state_before: Dict[str, Any] = field(default_factory=dict)
    state_after: Dict[str, Any] = field(default_factory=dict)

    # References to governance artifacts produced during this session
    decisions: List[str] = field(
        default_factory=list
    )  # MindEvent IDs of DECISION_MADE events
    traces: List[str] = field(default_factory=list)  # ReasoningTrace IDs
    intents_patched: List[str] = field(default_factory=list)  # IntentCard IDs modified

    # Meeting governance fields
    status: MeetingStatus = MeetingStatus.PLANNED
    meeting_type: str = "general"
    agenda: List[str] = field(default_factory=list)
    success_criteria: List[str] = field(default_factory=list)
    round_count: int = 0
    max_rounds: int = 5
    action_items: List[Dict[str, Any]] = field(default_factory=list)
    minutes_md: str = ""

    metadata: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def new(
        workspace_id: str,
        project_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        lens_id: Optional[str] = None,
        state_before: Optional[Dict[str, Any]] = None,
        meeting_type: str = "general",
        agenda: Optional[List[str]] = None,
        success_criteria: Optional[List[str]] = None,
        max_rounds: int = 5,
    ) -> "MeetingSession":
        return MeetingSession(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            project_id=project_id,
            thread_id=thread_id,
            lens_id=lens_id,
            state_before=state_before or {},
            meeting_type=meeting_type or "general",
            agenda=list(agenda or []),
            success_criteria=list(success_criteria or []),
            max_rounds=max_rounds,
        )

    def start(self) -> None:
        """Transition session to ACTIVE."""
        if self.status == MeetingStatus.PLANNED:
            self.status = MeetingStatus.ACTIVE

    def begin_closing(self) -> None:
        """Transition session to CLOSING."""
        if self.status in (MeetingStatus.PLANNED, MeetingStatus.ACTIVE):
            self.status = MeetingStatus.CLOSING

    def end(self, state_after: Optional[Dict[str, Any]] = None) -> None:
        """Mark this session as ended."""
        self.ended_at = datetime.now(timezone.utc)
        if state_after:
            self.state_after = state_after

    def close(self, state_after: Optional[Dict[str, Any]] = None) -> None:
        """Transition session to CLOSED and set end timestamp."""
        self.status = MeetingStatus.CLOSED
        self.end(state_after=state_after)

    def abort(self, reason: Optional[str] = None) -> None:
        """Transition session to ABORTED and set end timestamp."""
        self.status = MeetingStatus.ABORTED
        if reason:
            self.metadata["abort_reason"] = reason
        self.end()

    @property
    def state_diff(self) -> Dict[str, Any]:
        """Compute diff between state_before and state_after."""
        if not self.state_before or not self.state_after:
            return {}
        diff: Dict[str, Any] = {}
        all_keys = set(self.state_before.keys()) | set(self.state_after.keys())
        for key in all_keys:
            before = self.state_before.get(key)
            after = self.state_after.get(key)
            if before != after:
                diff[key] = {"before": before, "after": after}
        return diff

    @property
    def is_active(self) -> bool:
        return self.ended_at is None and self.status in (
            MeetingStatus.PLANNED,
            MeetingStatus.ACTIVE,
            MeetingStatus.CLOSING,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "thread_id": self.thread_id,
            "lens_id": self.lens_id,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "state_before": self.state_before,
            "state_after": self.state_after,
            "state_diff": self.state_diff,
            "decisions": self.decisions,
            "traces": self.traces,
            "intents_patched": self.intents_patched,
            "status": (
                self.status.value if hasattr(self.status, "value") else self.status
            ),
            "meeting_type": self.meeting_type,
            "agenda": self.agenda,
            "success_criteria": self.success_criteria,
            "round_count": self.round_count,
            "max_rounds": self.max_rounds,
            "action_items": self.action_items,
            "minutes_md": self.minutes_md,
            "is_active": self.is_active,
            "metadata": self.metadata,
        }
