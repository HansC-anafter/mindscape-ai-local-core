"""
Compile job model for handoff bundle meeting compilation.

Represents the lifecycle of a compile request independent of whether the
underlying route is currently synchronous or asynchronous.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

INTERNAL_METADATA_PREFIX = "_internal_"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CompileJobStatus(str, Enum):
    """Lifecycle status for a handoff compile job."""

    ACCEPTED = "accepted"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass
class CompileJob:
    """A compile job for handoff bundle intake and meeting compilation."""

    id: str
    workspace_id: str
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
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @staticmethod
    def new(
        workspace_id: str,
        project_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        session_id: Optional[str] = None,
        handoff_id: Optional[str] = None,
        source_device_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "CompileJob":
        return CompileJob(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            project_id=project_id,
            thread_id=thread_id,
            profile_id=profile_id,
            session_id=session_id,
            handoff_id=handoff_id,
            source_device_id=source_device_id,
            metadata=dict(metadata or {}),
        )

    def mark_running(
        self,
        *,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.status = CompileJobStatus.RUNNING
        self.started_at = self.started_at or _utc_now()
        self.updated_at = _utc_now()
        if session_id:
            self.session_id = session_id
        if metadata:
            self.metadata.update(metadata)

    def mark_succeeded(
        self,
        *,
        session_id: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.status = CompileJobStatus.SUCCEEDED
        self.updated_at = _utc_now()
        self.completed_at = self.updated_at
        if session_id:
            self.session_id = session_id
        if result is not None:
            self.result = dict(result)
        self.error = None
        if metadata:
            self.metadata.update(metadata)

    def mark_failed(
        self,
        error: str,
        *,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.status = CompileJobStatus.FAILED
        self.updated_at = _utc_now()
        self.completed_at = self.updated_at
        if session_id:
            self.session_id = session_id
        self.error = error
        if metadata:
            self.metadata.update(metadata)

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
            "status": self.status.value if hasattr(self.status, "value") else self.status,
            "result": self.result,
            "error": self.error,
            "metadata": self.public_metadata(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    def public_metadata(self) -> Dict[str, Any]:
        return {
            key: value
            for key, value in (self.metadata or {}).items()
            if not str(key).startswith(INTERNAL_METADATA_PREFIX)
        }
