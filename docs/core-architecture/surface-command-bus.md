# Surface & Command Bus Core Architecture

Surface represents input/output channels (UI, LINE, IG, WordPress, etc.). Command Bus provides unified command dispatch and tracking across all surfaces.

**Last updated**: 2025-12-22

---

## Overview

Surface & Command Bus architecture provides a unified way to handle commands and events from different input/output channels. It separates the concept of "Control Surface" (for builders/operators) from "Delivery Surface" (for end users/audience).

**Key Characteristics**:
- Unified command dispatch across all surfaces
- Support for approval workflows
- Event stream collection and querying
- Surface type classification (Control vs Delivery)
- BYOP/BYOL metadata tracking

---

## Surface Classification

### Control Surface

**Purpose**: Building, management, debugging, approval, rollback, version management.

**Characteristics**:
- For Builder/Operator/Admin
- Primary behavior: orchestration
- Requires fine-grained control and traceability
- Higher permissions (can configure, approve, rollback)

**Examples**:
- mindscape-ai-ui (Web Console)
- Agency Console (future)
- Admin Dashboard
- CLI Tool

**Code Reference**: `backend/app/routes/core/surface.py:30-46`

### Delivery Surface

**Purpose**: Reply/publish/display to end users or audience.

**Characteristics**:
- For end users or audience
- Primary behavior: consumption
- Focuses on usability and accessibility
- Lower permissions (can only execute predefined operations)

**Examples**:
- LINE Official Account
- Instagram
- WordPress public pages
- Email notifications
- Webhook callbacks

**Code Reference**: `backend/app/routes/core/surface.py:49-95`

---

## Core Models

### SurfaceDefinition

Surface definition contract.

**Location**: `backend/app/models/surface.py:25-34`

```python
class SurfaceDefinition(BaseModel):
    surface_id: str
    surface_type: SurfaceType
    display_name: str
    capabilities: List[str]
    permission_level: PermissionLevel
    adapter_class: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
```

**Fields**:
- `surface_id`: Unique surface identifier
- `surface_type`: Surface type (CONTROL or DELIVERY)
- `display_name`: Human-readable display name
- `capabilities`: List of capability strings
- `permission_level`: Permission level (CONSUMER, OPERATOR, ADMIN)
- `adapter_class`: Optional adapter class path (provided by cloud layer)
- `metadata`: Additional metadata

### Command

Command model for Command Bus.

**Location**: `backend/app/models/surface.py:46-73`

```python
class Command(BaseModel):
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
        description="Metadata including: card_id, pack_id, scope, playbook_version (for BYOP/BYOL)"
    )
    created_at: datetime
    updated_at: datetime
```

**Fields**:
- `command_id`: Unique command identifier
- `workspace_id`: Workspace ID
- `actor_id`: Actor ID (user who issued the command)
- `source_surface`: Source surface ID
- `intent_code`: Intent code (playbook code)
- `parameters`: Command parameters
- `requires_approval`: Whether approval is required
- `status`: Command status (PENDING, APPROVED, RUNNING, COMPLETED, FAILED, REJECTED)
- `execution_id`: Associated execution ID
- `thread_id`: Thread ID for conversation threading
- `correlation_id`: Correlation ID for request tracking
- `metadata`: Metadata including BYOP/BYOL fields (card_id, pack_id, scope, playbook_version)

### SurfaceEvent

Event model for Surface Event Stream.

**Location**: `backend/app/models/surface.py:76-100`

```python
class SurfaceEvent(BaseModel):
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
    created_at: datetime
```

**Fields**:
- `event_id`: Unique event identifier
- `workspace_id`: Workspace ID
- `source_surface`: Source surface ID
- `event_type`: Event type
- `actor_id`: Optional actor ID
- `payload`: Event payload
- `command_id`: Optional associated command ID
- `thread_id`: Thread ID for conversation threading
- `correlation_id`: Correlation ID for request tracking
- `pack_id`, `card_id`, `scope`, `playbook_version`: BYOP/BYOL fields (flattened for efficient querying)

### Enums

**SurfaceType**: Surface type classification
- `CONTROL`: Control surface
- `DELIVERY`: Delivery surface

**PermissionLevel**: Permission level for surface operations
- `CONSUMER`: Consumer level (lowest)
- `OPERATOR`: Operator level
- `ADMIN`: Admin level (highest)

**CommandStatus**: Command execution status
- `PENDING`: Pending approval
- `APPROVED`: Approved, ready to execute
- `RUNNING`: Currently executing
- `COMPLETED`: Execution completed
- `FAILED`: Execution failed
- `REJECTED`: Rejected

**Location**: `backend/app/models/surface.py:12-43`

---

## Core Services

### CommandBus

Central command bus for all surfaces.

**Location**: `backend/app/services/surface/command_bus.py`

**Key Methods**:

- `dispatch_command(command: Command) -> Dict[str, Any]`: Dispatch a command from any surface
- `approve_command(command_id: str) -> Dict[str, Any]`: Approve a pending command
- `reject_command(command_id: str, reason: Optional[str]) -> Dict[str, Any]`: Reject a pending command
- `get_command(command_id: str) -> Optional[Command]`: Get command by ID
- `list_commands(workspace_id: Optional[str], status: Optional[CommandStatus], limit: int) -> List[Command]`: List commands with filters

**Code Reference**: `backend/app/services/surface/command_bus.py:66-289`

**Approval Flow**:
1. Command with `requires_approval=True` is set to `PENDING` status
2. Command waits for approval via `approve_command()`
3. Once approved, command is executed
4. Execution result is recorded with `execution_id`

**BYOP/BYOL Support**:
- Automatically extracts BYOP/BYOL fields from `command.parameters` and records in `command.metadata`
- Persists BYOP/BYOL metadata to execution trace after execution
- Fields: `pack_id`, `card_id`, `scope`, `playbook_version`

### EventStreamService

Service for managing Surface event stream.

**Location**: `backend/app/services/surface/event_stream.py`

**Key Methods**:

- `collect_event(workspace_id: str, source_surface: str, event_type: str, payload: Dict[str, Any], ...) -> SurfaceEvent`: Collect an event from any surface
- `get_events(workspace_id: str, surface_filter: Optional[str], event_type_filter: Optional[str], ...) -> List[SurfaceEvent]`: Get events with filters

**Code Reference**: `backend/app/services/surface/event_stream.py:14-144`

**BYOP/BYOL Support**:
- Automatically extracts BYOP/BYOL fields from `payload` and flattens to event fields
- Supports filtering by `pack_id` and `card_id`
- Fields: `pack_id`, `card_id`, `scope`, `playbook_version`

### SurfaceRegistry

Registry for surface definitions.

**Location**: `backend/app/services/surface/command_bus.py:23-64`

**Key Methods**:

- `register_surface(surface: SurfaceDefinition) -> SurfaceDefinition`: Register a surface
- `get_surface(surface_id: str) -> Optional[SurfaceDefinition]`: Get surface by ID
- `list_surfaces() -> List[SurfaceDefinition]`: List all registered surfaces

**Default Surfaces**:
- `mindscape_ui`: Control surface (Web Console)
- `line`: Delivery surface (LINE Official Account)
- `ig`: Delivery surface (Instagram)
- `wordpress_public`: Delivery surface (WordPress)

**Code Reference**: `backend/app/routes/core/surface.py:22-98`

---

## API Routes

### Base Path

`/api/v1`

**Location**: `backend/app/routes/core/surface.py`

### Command Endpoints

#### POST `/api/v1/commands`

Dispatch a command from any surface.

**Request Body**: `Command`

**Response**: `Dict[str, Any]` (201 Created)
```python
{
    "command_id": str,
    "status": "pending_approval" | "completed",
    "execution_id": Optional[str],
    "message": Optional[str]
}
```

**Code Reference**: `backend/app/routes/core/surface.py:101-114`

#### POST `/api/v1/commands/{command_id}/approve`

Approve a pending command.

**Response**: `Dict[str, Any]`
```python
{
    "command_id": str,
    "execution_id": str,
    "status": "completed"
}
```

**Code Reference**: `backend/app/routes/core/surface.py:117-129`

#### POST `/api/v1/commands/{command_id}/reject`

Reject a pending command.

**Request Body**: `{"reason": Optional[str]}`

**Response**: `Dict[str, Any]`
```python
{
    "command_id": str,
    "status": "rejected",
    "reason": Optional[str]
}
```

**Code Reference**: `backend/app/routes/core/surface.py:132-147`

#### GET `/api/v1/commands/{command_id}`

Get command by ID.

**Response**: `Command`

**Code Reference**: `backend/app/routes/core/surface.py:150-160`

#### GET `/api/v1/commands`

List commands with filters.

**Query Parameters**:
- `workspace_id` (optional): Filter by workspace ID
- `status` (optional): Filter by status
- `limit` (default: 50): Maximum number of results

**Response**: `List[Command]`

**Code Reference**: `backend/app/routes/core/surface.py:163-174`

### Event Endpoints

#### POST `/api/v1/events`

Collect an event from any surface.

**Request Body**:
```python
{
    "workspace_id": str,
    "source_surface": str,
    "event_type": str,
    "payload": Dict[str, Any],
    "actor_id": Optional[str],
    "command_id": Optional[str],
    "thread_id": Optional[str],
    "correlation_id": Optional[str],
    "parent_event_id": Optional[str],
    "execution_id": Optional[str]
}
```

**Response**: `SurfaceEvent` (201 Created)

**Code Reference**: `backend/app/routes/core/surface.py:177-209`

#### GET `/api/v1/events`

Get events with filters.

**Query Parameters**:
- `workspace_id` (required): Workspace ID
- `surface_filter` (optional): Filter by source surface
- `event_type_filter` (optional): Filter by event type
- `actor_filter` (optional): Filter by actor ID
- `command_id_filter` (optional): Filter by command ID
- `thread_id_filter` (optional): Filter by thread ID
- `correlation_id_filter` (optional): Filter by correlation ID
- `pack_id_filter` (optional): Filter by pack ID (BYOP)
- `card_id_filter` (optional): Filter by card ID (BYOP)
- `limit` (default: 50): Maximum number of results

**Response**: `List[SurfaceEvent]`

**Code Reference**: `backend/app/routes/core/surface.py:212-242`

### Surface Endpoints

#### POST `/api/v1/surfaces`

Register a surface.

**Request Body**: `SurfaceDefinition`

**Response**: `SurfaceDefinition` (201 Created)

**Code Reference**: `backend/app/routes/core/surface.py:245-255`

#### GET `/api/v1/surfaces/{surface_id}`

Get surface by ID.

**Response**: `SurfaceDefinition`

**Code Reference**: `backend/app/routes/core/surface.py:258-268`

#### GET `/api/v1/surfaces`

List all registered surfaces.

**Response**: `List[SurfaceDefinition]`

**Code Reference**: `backend/app/routes/core/surface.py:271-278`

---

## Usage Examples

### Example 1: Dispatch a Command

```python
from app.models.surface import Command, CommandStatus
from app.services.surface.command_bus import CommandBus

command_bus = CommandBus()

command = Command(
    command_id="cmd_001",
    workspace_id="workspace_001",
    actor_id="user_123",
    source_surface="mindscape_ui",
    intent_code="content_drafting",
    parameters={
        "topic": "Product introduction",
        "length": 500
    },
    requires_approval=False,
    status=CommandStatus.PENDING
)

result = await command_bus.dispatch_command(command)
# Returns: {"command_id": "cmd_001", "execution_id": "exec_001", "status": "completed"}
```

### Example 2: Command with Approval

```python
from app.models.surface import Command, CommandStatus
from app.services.surface.command_bus import CommandBus

command_bus = CommandBus()

# Create command requiring approval
command = Command(
    command_id="cmd_002",
    workspace_id="workspace_001",
    actor_id="user_123",
    source_surface="line",
    intent_code="publish_content",
    parameters={"content_id": "content_001"},
    requires_approval=True,
    status=CommandStatus.PENDING
)

# Dispatch (will be pending)
result = await command_bus.dispatch_command(command)
# Returns: {"command_id": "cmd_002", "status": "pending_approval", "message": "Command requires approval"}

# Approve and execute
result = await command_bus.approve_command("cmd_002")
# Returns: {"command_id": "cmd_002", "execution_id": "exec_002", "status": "completed"}
```

### Example 3: Collect an Event

```python
from app.services.surface.event_stream import EventStreamService

event_stream = EventStreamService()

event = event_stream.collect_event(
    workspace_id="workspace_001",
    source_surface="line",
    event_type="message_received",
    payload={
        "message": "Hello",
        "user_id": "line_user_123"
    },
    actor_id="line_user_123",
    thread_id="thread_001"
)
```

### Example 4: Query Events

```python
from app.services.surface.event_stream import EventStreamService

event_stream = EventStreamService()

# Get events from LINE surface
events = event_stream.get_events(
    workspace_id="workspace_001",
    surface_filter="line",
    limit=50
)

# Get events by thread
thread_events = event_stream.get_events(
    workspace_id="workspace_001",
    thread_id_filter="thread_001",
    limit=50
)

# Get events by BYOP pack
pack_events = event_stream.get_events(
    workspace_id="workspace_001",
    pack_id_filter="openseo_pack_v1",
    limit=50
)
```

### Example 5: Register a Custom Surface

```python
from app.models.surface import SurfaceDefinition, SurfaceType, PermissionLevel
from app.services.surface.command_bus import SurfaceRegistry

registry = SurfaceRegistry()

custom_surface = SurfaceDefinition(
    surface_id="custom_api",
    surface_type=SurfaceType.DELIVERY,
    display_name="Custom API",
    capabilities=["receive_message", "send_message"],
    permission_level=PermissionLevel.CONSUMER,
    metadata={"type": "api", "version": "1.0"}
)

registered = registry.register_surface(custom_surface)
```

---

## Integration Notes

### Surface Adapters

Surface adapters are implemented in the cloud layer, not in local-core. Local-core only provides:
- Surface definition contract (`SurfaceDefinition`)
- Command Bus service
- Event Stream service
- API routes

Adapter implementations (LINE, IG, WordPress, UI) are provided by the cloud layer.

### BYOP/BYOL Support

Command Bus and Event Stream automatically extract and record BYOP/BYOL fields:
- `pack_id`: Capability pack ID
- `card_id`: Execution card ID
- `scope`: Scope definition
- `playbook_version`: Playbook version

These fields are:
- Extracted from `command.parameters` or `event.payload`
- Recorded in `command.metadata` or flattened to event fields
- Persisted to execution trace for provenance tracking
- Available for filtering and querying

---

## Related Documentation

- [Execution Context Four-Layer Model](./execution-context-four-layer-model.md) - How Surface fits into the four-layer model
- [Execution Context](./execution-context.md) - Core ExecutionContext abstraction
- [System Overview](./system-overview.md) - Complete system architecture

---

**Last updated**: 2025-12-22
