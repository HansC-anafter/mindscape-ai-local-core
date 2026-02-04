"""Surface core contract definitions.

Surface represents input/output channels (UI, LINE, IG, WordPress, etc.)
Command Bus provides unified command dispatch and tracking across all surfaces.
"""

from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime


class SurfaceType(str, Enum):
    """Surface type classification."""

    CONTROL = "control"
    DELIVERY = "delivery"


class PermissionLevel(str, Enum):
    """Permission level for surface operations."""

    CONSUMER = "consumer"
    OPERATOR = "operator"
    ADMIN = "admin"


class SurfaceDefinition(BaseModel):
    """Surface definition contract."""

    surface_id: str
    surface_type: SurfaceType
    display_name: str
    capabilities: List[str]
    permission_level: PermissionLevel
    adapter_class: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CommandStatus(str, Enum):
    """Command execution status."""

    PENDING = "pending"
    APPROVED = "approved"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"


class Command(BaseModel):
    """
    Command model for Command Bus.

    Metadata field supports BYOP/BYOL collaboration:
    - card_id: Execution card ID (for scope tracking)
    - pack_id: Capability pack ID used
    - scope: Scope definition (intent_code/card_id/step_id)
    - playbook_version: Playbook version used
    """

    command_id: str
    workspace_id: str
    actor_id: str
    source_surface: str
    intent_code: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = False
    status: CommandStatus = CommandStatus.PENDING
    execution_id: Optional[str] = None
    thread_id: Optional[str] = None
    correlation_id: Optional[str] = None
    parent_command_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata including: card_id, pack_id, scope, playbook_version (for BYOP/BYOL)",
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class SurfaceEvent(BaseModel):
    """
    Event model for Surface Event Stream.

    BYOP/BYOL fields (pack_id, card_id, scope, playbook_version) are extracted
    from payload and stored as flattened columns for efficient querying.
    """

    event_id: str
    workspace_id: str
    source_surface: str
    event_type: str
    actor_id: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    command_id: Optional[str] = None
    thread_id: Optional[str] = None
    correlation_id: Optional[str] = None
    parent_event_id: Optional[str] = None
    execution_id: Optional[str] = None
    pack_id: Optional[str] = Field(None, description="Capability pack ID (BYOP)")
    card_id: Optional[str] = Field(None, description="Execution card ID (BYOP)")
    scope: Optional[str] = Field(None, description="Scope definition (BYOP)")
    playbook_version: Optional[str] = Field(None, description="Playbook version (BYOP)")
    timestamp: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ExternalContext(BaseModel):
    """External context from MCP Gateway for Intent/Seed tracking (P3).

    When external AI tools (Claude Desktop, Cursor) call Mindscape tools,
    they can pass conversation context to enable Intent/Seed extraction.
    """

    workspace_id: str
    surface_type: str = Field(
        description="External surface type (e.g., claude_desktop, cursor)"
    )
    surface_user_id: str = Field(description="User identifier from external surface")
    original_message: Optional[str] = Field(None, description="Original user message")
    tool_called: str = Field(description="MCP tool that was called")
    conversation_id: Optional[str] = Field(
        None, description="Conversation ID from external surface"
    )
    intent_hint: Optional[str] = Field(
        None, description="Intent hint from external LLM"
    )
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ExternalContextResponse(BaseModel):
    """Response from external context recording."""

    success: bool = True
    intent_id: Optional[str] = None
    seed_id: Optional[str] = None
    event_id: Optional[str] = None
    message: Optional[str] = None
