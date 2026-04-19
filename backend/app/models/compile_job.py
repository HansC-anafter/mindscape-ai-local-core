"""
Compile job model for long-running handoff/meeting compiles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


class CompileJobStatus(str, Enum):
    ACCEPTED = "accepted"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass
class CompileJob:
    id: str
    workspace_id: Optional[str] = None
    project_id: Optional[str] = None
    thread_id: Optional[str] = None
    profile_id: Optional[str] = None
    session_id: Optional[str] = None
    handoff_id: Optional[str] = None
    source_device_id: Optional[str] = None
    status: CompileJobStatus = CompileJobStatus.ACCEPTED
    result: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "thread_id": self.thread_id,
            "profile_id": self.profile_id,
            "session_id": self.session_id,
            "handoff_id": self.handoff_id,
            "source_device_id": self.source_device_id,
            "status": self.status.value if hasattr(self.status, "value") else str(self.status),
            "result": self.result,
            "error": self.error,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
