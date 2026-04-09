"""
ProgramRun model for persistent long-horizon meeting outputs.

This is the minimal durable ledger that lifts ProgramSpec out of transient
meeting-session metadata. It does not yet manage multi-session resume, but it
does record the structured program artifact plus the current bounded cursor
state so later runtime layers can build on it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProgramRunStatus(str, Enum):
    """Lifecycle status for a persisted program ledger."""

    OPEN = "open"
    COMPLETED = "completed"


@dataclass
class ProgramRun:
    """Durable record of a ProgramSpec produced by a bounded meeting."""

    id: str
    workspace_id: str
    meeting_session_id: str
    project_id: Optional[str] = None
    thread_id: Optional[str] = None
    status: ProgramRunStatus = ProgramRunStatus.OPEN
    source: str = "action_intent_bootstrap"
    scale: Optional[str] = None
    program_spec: Dict[str, Any] = field(default_factory=dict)
    cursor_state: Dict[str, Any] = field(default_factory=dict)
    target_outputs: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)
    recorded_at: datetime = field(default_factory=_utc_now)

    @staticmethod
    def new(
        *,
        workspace_id: str,
        meeting_session_id: str,
        project_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        status: ProgramRunStatus = ProgramRunStatus.OPEN,
        source: str = "action_intent_bootstrap",
        scale: Optional[str] = None,
        program_spec: Optional[Dict[str, Any]] = None,
        cursor_state: Optional[Dict[str, Any]] = None,
        target_outputs: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        program_run_id: Optional[str] = None,
    ) -> "ProgramRun":
        now = _utc_now()
        return ProgramRun(
            id=program_run_id or str(uuid.uuid4()),
            workspace_id=workspace_id,
            meeting_session_id=meeting_session_id,
            project_id=project_id,
            thread_id=thread_id,
            status=status,
            source=source,
            scale=scale,
            program_spec=dict(program_spec or {}),
            cursor_state=dict(cursor_state or {}),
            target_outputs=list(target_outputs or []),
            metadata=dict(metadata or {}),
            created_at=now,
            updated_at=now,
            recorded_at=now,
        )

    @property
    def workstream_count(self) -> int:
        workstreams = self.program_spec.get("workstreams")
        return len(workstreams) if isinstance(workstreams, list) else 0

    @property
    def milestone_count(self) -> int:
        milestones = self.program_spec.get("milestones")
        return len(milestones) if isinstance(milestones, list) else 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "meeting_session_id": self.meeting_session_id,
            "project_id": self.project_id,
            "thread_id": self.thread_id,
            "status": self.status.value if hasattr(self.status, "value") else self.status,
            "source": self.source,
            "scale": self.scale,
            "program_spec": self.program_spec,
            "cursor_state": self.cursor_state,
            "target_outputs": self.target_outputs,
            "metadata": self.metadata,
            "workstream_count": self.workstream_count,
            "milestone_count": self.milestone_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "recorded_at": self.recorded_at.isoformat(),
        }
