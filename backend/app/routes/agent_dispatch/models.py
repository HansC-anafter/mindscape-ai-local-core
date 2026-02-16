"""
Agent Dispatch — Data models and request/response schemas.

Contains dataclasses for internal state tracking (clients, tasks, leases)
and Pydantic models for REST API request/response validation.
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, ClassVar, Dict, List, Optional

from pydantic import BaseModel, Field


# ============================================================
#  Internal data classes
# ============================================================


@dataclass
class AgentClient:
    """Represents a connected IDE agent client."""

    websocket: Any  # fastapi.WebSocket (typed as Any to avoid import)
    client_id: str
    workspace_id: str
    surface_type: str  # e.g. "gemini_cli", "cursor", "windsurf"
    connected_at: float = field(default_factory=time.monotonic)
    last_heartbeat: float = field(default_factory=time.monotonic)
    authenticated: bool = False


@dataclass
class AgentControlClient:
    """Represents a connected bridge control client."""

    websocket: Any  # fastapi.WebSocket
    bridge_id: str
    owner_user_id: Optional[str] = None
    connected_at: float = field(default_factory=time.monotonic)
    last_heartbeat: float = field(default_factory=time.monotonic)


@dataclass
class PendingTask:
    """A task waiting to be dispatched to an IDE client."""

    execution_id: str
    workspace_id: str
    payload: Dict[str, Any]
    created_at: float = field(default_factory=time.monotonic)
    target_client_id: Optional[str] = None
    attempts: int = 0
    max_attempts: int = 3


@dataclass
class InflightTask:
    """A task currently being executed by an IDE client."""

    execution_id: str
    workspace_id: str
    client_id: str
    dispatched_at: float = field(default_factory=time.monotonic)
    acked: bool = False
    result_future: Optional[asyncio.Future] = None
    payload: Optional[Dict[str, Any]] = None  # retained for re-queue on disconnect


@dataclass
class ReservedTask:
    """A task reserved by a polling client with lease timeout."""

    task: PendingTask
    client_id: str
    lease_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    reserved_at: float = field(default_factory=time.monotonic)
    lease_seconds: float = 30.0
    acked: bool = False
    cumulative_lease: float = 0.0

    # Max cumulative lease per task (30 minutes)
    MAX_CUMULATIVE_LEASE: ClassVar[float] = 1800.0

    @property
    def lease_deadline(self) -> float:
        return self.reserved_at + self.lease_seconds

    @property
    def expired(self) -> bool:
        return time.monotonic() > self.lease_deadline

    def extend_lease(self, seconds: float) -> bool:
        """Extend lease. Returns False if cumulative cap exceeded."""
        if self.cumulative_lease + seconds > self.MAX_CUMULATIVE_LEASE:
            return False
        self.lease_seconds += seconds
        self.cumulative_lease += seconds
        return True

    def reset_lease(self, seconds: float) -> bool:
        """Reset lease timer from now. Returns False if cap exceeded."""
        now = time.monotonic()
        elapsed = now - self.reserved_at
        new_total = elapsed + seconds
        if self.cumulative_lease + seconds > self.MAX_CUMULATIVE_LEASE:
            return False
        self.lease_seconds = new_total
        self.cumulative_lease += seconds
        return True


# ============================================================
#  Pydantic request/response schemas (REST API)
# ============================================================


class AgentResultRequest(BaseModel):
    """Request body for submitting agent execution results."""

    execution_id: str = Field(..., description="Execution ID")
    status: str = Field(
        default="completed",
        description="Execution status: completed | failed",
    )
    output: str = Field(
        default="", description="Human-readable summary (max 500 chars)"
    )
    result_json: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Structured result payload for persistence",
    )
    attachments: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Files to persist with the result [{filename, content, encoding?}]",
    )
    duration_seconds: float = Field(default=0, description="Duration in seconds")
    tool_calls: list = Field(default_factory=list, description="Tools invoked")
    files_modified: list = Field(
        default_factory=list,
        description="Files modified during execution",
    )
    files_created: list = Field(
        default_factory=list,
        description="Files created during execution",
    )
    error: Optional[str] = Field(default=None, description="Error message if failed")
    client_id: Optional[str] = Field(
        default=None,
        description="Client ID for ownership verification on reserved tasks",
    )
    lease_id: Optional[str] = Field(
        default=None,
        description="Lease ID for ownership verification",
    )
    governance: dict = Field(
        default_factory=dict,
        description="Governance trace (output_hash, summary, etc.)",
    )
    metadata: dict = Field(
        default_factory=dict,
        description="Client metadata (executor_location, surface_type, etc.)",
    )


class AgentResultResponse(BaseModel):
    """Response for agent result submission."""

    accepted: bool
    execution_id: str
    message: str = ""


class AckRequest(BaseModel):
    execution_id: str
    lease_id: str
    client_id: Optional[str] = None


class ProgressRequest(BaseModel):
    execution_id: str
    lease_id: str
    progress_pct: Optional[float] = None
    message: Optional[str] = None
    client_id: Optional[str] = None
