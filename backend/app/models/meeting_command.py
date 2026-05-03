"""Contracts for Meeting Workbench command-envelope ledger rows."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.object_runtime import ObjectRoleEntry


MeetingCommandActor = Literal["user", "agent", "pack", "system"]
MeetingCommandWriteMode = Literal[
    "recommendation_only",
    "proposal_only",
    "canonical_with_review",
    "staged",
]


class MeetingCommandStatus(str, Enum):
    """Durable command lifecycle status."""

    DRAFTED = "drafted"
    ACCEPTED = "accepted"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SUPERSEDED = "superseded"


class MeetingRequestedAction(BaseModel):
    """Normalized tool/workflow request carried by a meeting command."""

    model_config = ConfigDict(extra="forbid")

    verb: Optional[str] = None
    pack_code: Optional[str] = None
    playbook_code: Optional[str] = None
    affordance_verb: Optional[str] = None
    write_mode: Optional[MeetingCommandWriteMode] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)


class MeetingCommandEnvelope(BaseModel):
    """Client/server contract for submitting a meeting command."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: Optional[str] = None
    meeting_id: str = Field(min_length=1)
    command_id: Optional[str] = None
    client_draft_id: Optional[str] = None
    origin_surface: str = Field(default="meeting_workbench", min_length=1)
    actor: MeetingCommandActor = "user"
    intent_text: str = Field(min_length=1)
    context_objects: List[ObjectRoleEntry] = Field(default_factory=list)
    requested_action: Optional[MeetingRequestedAction] = None
    expected_outputs: List[str] = Field(default_factory=list)
    write_mode: MeetingCommandWriteMode = "recommendation_only"
    thread_id: Optional[str] = None
    meeting_mentions: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MeetingCommandRecord(BaseModel):
    """Persisted command-ledger row."""

    model_config = ConfigDict(extra="forbid")

    command_id: str
    workspace_id: str
    meeting_id: str
    thread_id: Optional[str] = None
    client_draft_id: Optional[str] = None
    origin_surface: str
    actor: MeetingCommandActor
    intent_text: str
    context_objects: List[ObjectRoleEntry] = Field(default_factory=list)
    requested_action: Optional[MeetingRequestedAction] = None
    expected_outputs: List[str] = Field(default_factory=list)
    write_mode: MeetingCommandWriteMode = "recommendation_only"
    status: MeetingCommandStatus = MeetingCommandStatus.ACCEPTED
    accepted_task_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MeetingCommandAcceptResponse(BaseModel):
    """Response for accepted command-envelope submissions."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    meeting_id: str
    command_id: str
    status: MeetingCommandStatus
    command: MeetingCommandRecord
    dispatch_result: Optional[Dict[str, Any]] = None


class MeetingCommandListResponse(BaseModel):
    """Command-ledger read response for one meeting session."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    meeting_id: str
    commands: List[MeetingCommandRecord] = Field(default_factory=list)
