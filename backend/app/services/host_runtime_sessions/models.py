"""Canonical host runtime session models.

This module is the contract boundary between the backend gateway, host bridge,
and AOL graph RUNS surface. It intentionally models session/turn/item lifecycle
events instead of terminal stdout.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


RuntimeSurface = Literal["codex_cli", "gemini_cli"]
SessionStatus = Literal[
    "created",
    "ready",
    "running",
    "bridge_unavailable",
    "bridge_disconnected",
    "interrupted",
    "closed",
    "failed",
]
TurnStatus = Literal[
    "queued",
    "running",
    "approval_required",
    "bridge_unavailable",
    "interrupted",
    "completed",
    "failed",
    "governance_blocked",
]

CANONICAL_EVENT_TYPES = {
    "session.created",
    "session.ready",
    "turn.started",
    "item.started",
    "assistant.delta",
    "assistant.message.completed",
    "tool.started",
    "tool.output.delta",
    "tool.completed",
    "approval.requested",
    "approval.approved",
    "approval.denied",
    "approval.resolved",
    "governance.audit.recorded",
    "governance.snapshot.recorded",
    "patch.proposed",
    "artifact.provenance.recorded",
    "file.changed",
    "layout.intent",
    "layout.accepted",
    "layout.rejected",
    "layout.overridden",
    "layout.reset",
    "layout.locked",
    "layout.snapshot.saved",
    "turn.completed",
    "turn.failed",
    "session.interrupted",
    "session.closed",
    "connection_lost",
}

TOKEN_DELTA_EVENT_TYPES = {"assistant.delta", "tool.output.delta"}
MAX_PERSISTED_EVENT_PAYLOAD_BYTES = 16 * 1024


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def new_uuid() -> str:
    return str(uuid4())


class HostRuntimeSession(BaseModel):
    id: str = Field(default_factory=new_uuid)
    execution_id: str = Field(default_factory=lambda: new_id("exec"))
    workspace_id: str
    actor_id: Optional[str] = None
    runtime_surface: RuntimeSurface = "codex_cli"
    runtime_id: str = "codex_cli"
    bridge_id: Optional[str] = None
    app_server_thread_id: Optional[str] = None
    status: SessionStatus = "created"
    cwd: str
    created_by: Optional[str] = None
    active_turn_id: Optional[str] = None
    last_event_seq: int = 0
    governance_trace_ref: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    terminal_at: Optional[datetime] = None


class HostRuntimeTurn(BaseModel):
    id: str = Field(default_factory=new_uuid)
    session_id: str
    workspace_id: str
    status: TurnStatus = "queued"
    prompt_hash: str
    compiled_prompt_hash: Optional[str] = None
    intent_ref: dict[str, Any] = Field(default_factory=dict)
    lens_ref: dict[str, Any] = Field(default_factory=dict)
    policy_ref: dict[str, Any] = Field(default_factory=dict)
    context_ref: dict[str, Any] = Field(default_factory=dict)
    artifact_ref: dict[str, Any] = Field(default_factory=dict)
    approval_audit_ref: dict[str, Any] = Field(default_factory=dict)
    governance_trace_ref: Optional[str] = None
    started_at: datetime = Field(default_factory=utc_now)
    terminal_at: Optional[datetime] = None


class HostRuntimeEvent(BaseModel):
    id: Optional[int] = None
    workspace_id: str
    session_id: str
    turn_id: Optional[str] = None
    seq: Optional[int] = None
    event_type: str
    item_id: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    persist: bool = True


class HostRuntimeExecutionEnvelope(BaseModel):
    execution_id: str
    workspace_id: str
    session_id: str
    turn_id: str
    actor_id: Optional[str] = None
    trace_id: str
    runtime_surface: RuntimeSurface = "codex_cli"
    runtime_id: str = "codex_cli"
    prompt_hash: str
    compiled_prompt_hash: str
    intent_ref: dict[str, Any]
    lens_ref: dict[str, Any]
    policy_ref: dict[str, Any]
    context_ref: dict[str, Any]
    artifact_ref: dict[str, Any]
    governance_trace_ref: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class HostRuntimeBridgeSnapshot(BaseModel):
    bridge_id: str
    runtime_surface: RuntimeSurface = "codex_cli"
    runtime_id: str = "codex_cli"
    status: Literal["online", "offline"] = "online"
    workspace_ids: list[str] = Field(default_factory=list)
    connected_at: datetime = Field(default_factory=utc_now)
    last_heartbeat_at: datetime = Field(default_factory=utc_now)
    capabilities: dict[str, Any] = Field(default_factory=dict)
