# Mind Lens Core Architecture

Mind Lens represents perspective/viewpoint - how to see, where to focus attention, how to make trade-offs. It is distinct from Policy (constraints) - Lens is like driving style, Policy is like guardrails.

**Last updated**: 2025-12-22

---

## Overview

Mind Lens is a core abstraction for representing different perspectives and viewpoints in execution context. It allows the same task to be executed with different lenses, producing different results based on the chosen perspective.

**Key Characteristics**:
- Lens is execution context, not part of task
- Lens can be stacked, weighted, scoped
- Lens is replaceable and versionable
- Lens focuses on "how to interpret" not "what cannot be done"

---

## Core Models

### MindLensSchema

Professional-level schema defining dimensions for a role perspective.

**Location**: `backend/app/models/mind_lens.py:28-36`

```python
class MindLensSchema(BaseModel):
    schema_id: str
    role: str
    label: Optional[str] = None
    dimensions: List[Dimension]
    version: str = "0.1"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
```

**Fields**:
- `schema_id`: Unique schema identifier
- `role`: Professional role (e.g., "writer", "designer", "director")
- `label`: Human-readable label
- `dimensions`: List of perspective dimensions
- `version`: Schema version

### MindLensInstance

Personal/author-level instance of a Mind Lens (perspective/viewpoint).

**Location**: `backend/app/models/mind_lens.py:39-51`

```python
class MindLensInstance(BaseModel):
    mind_lens_id: str
    schema_id: str
    owner_user_id: str
    role: str
    label: Optional[str] = None
    description: Optional[str] = None
    values: Dict[str, Any]
    source: Optional[Dict[str, Any]] = None
    version: str = "0.1"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
```

**Fields**:
- `mind_lens_id`: Unique instance identifier
- `schema_id`: Reference to MindLensSchema
- `owner_user_id`: Owner user ID
- `role`: Professional role
- `values`: Dimension values (personalized settings)
- `source`: Source data (optional)

### RuntimeMindLens

Resolved Mind Lens for runtime execution context.

**Location**: `backend/app/models/mind_lens.py:54-63`

```python
class RuntimeMindLens(BaseModel):
    resolved_mind_lens_id: str
    role: str
    source_lenses: List[str]
    values: Dict[str, Any]
    bound_brains: Optional[List[str]] = None
    weights: Optional[Dict[str, float]] = None
    created_at: Optional[datetime] = None
```

**Fields**:
- `resolved_mind_lens_id`: Resolved lens identifier
- `role`: Professional role
- `source_lenses`: List of source lens IDs
- `values`: Resolved dimension values
- `weights`: Optional weights for multi-lens scenarios

### LensSpec

Executable Lens specification for compilation.

**Location**: `backend/app/models/mind_lens.py:65-97`

```python
class LensSpec(BaseModel):
    lens_id: str
    version: str
    category: str
    applies_to: List[str]
    inject: Dict[str, Any]
    params_schema: Dict[str, Any]
    transformers: Optional[List[str]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
```

**Fields**:
- `lens_id`: Lens identifier (e.g., "writer.hemingway")
- `category`: Category (writer, designer, director, etc.)
- `applies_to`: Modalities this lens applies to (text, image, audio, etc.)
- `inject`: Injection rules for compilation (system, style_rules, prompt_prefix, prompt_suffix)
- `params_schema`: Parameter schema for lens customization

---

## Core Services

### MindLensService

Service for managing Mind Lens schemas and instances.

**Location**: `backend/app/services/lens/mind_lens_service.py`

**Key Methods**:

#### Schema Management

- `create_schema(schema: MindLensSchema) -> MindLensSchema`: Create a new schema
- `get_schema(schema_id: str) -> Optional[MindLensSchema]`: Get schema by ID
- `get_schema_by_role(role: str) -> Optional[MindLensSchema]`: Get schema by role

#### Instance Management

- `create_instance(instance: MindLensInstance) -> MindLensInstance`: Create a new instance
- `get_instance(instance_id: str) -> Optional[MindLensInstance]`: Get instance by ID
- `update_instance(instance_id: str, updates: dict) -> Optional[MindLensInstance]`: Update instance
- `list_instances(owner_user_id: Optional[str], role: Optional[str], limit: int) -> List[MindLensInstance]`: List instances with filters

#### Resolution

- `resolve_lens(user_id: str, workspace_id: str, playbook_id: Optional[str], role_hint: Optional[str]) -> Optional[RuntimeMindLens]`: Resolve Mind Lens for execution context

**Code Reference**: `backend/app/services/lens/mind_lens_service.py:13-171`

---

## API Routes

### Base Path

`/api/v1/lenses`

**Location**: `backend/app/routes/core/lens.py`

### Endpoints

#### GET `/api/v1/lenses/schemas/{role}`

Get Mind Lens schema for a role.

**Response**: `MindLensSchema`

**Code Reference**: `backend/app/routes/core/lens.py:26-36`

#### GET `/api/v1/lenses/instances/{instance_id}`

Get Mind Lens instance by ID.

**Response**: `MindLensInstance`

**Code Reference**: `backend/app/routes/core/lens.py:39-49`

#### POST `/api/v1/lenses/instances`

Create a new Mind Lens instance.

**Request Body**: `MindLensInstance`

**Response**: `MindLensInstance` (201 Created)

**Code Reference**: `backend/app/routes/core/lens.py:52-62`

#### PUT `/api/v1/lenses/instances/{instance_id}`

Update a Mind Lens instance.

**Request Body**: `Dict[str, Any]` (update fields)

**Response**: `MindLensInstance`

**Code Reference**: `backend/app/routes/core/lens.py:65-78`

#### POST `/api/v1/lenses/resolve`

Resolve Mind Lens for execution context.

**Request Body**: `ResolveRequest`
```python
{
    "user_id": str,
    "workspace_id": str,
    "playbook_id": Optional[str],
    "role_hint": Optional[str]
}
```

**Response**: `RuntimeMindLens`

**Code Reference**: `backend/app/routes/core/lens.py:81-96`

---

## Contract Tests

Contract tests ensure API compatibility and core functionality.

**Location**: `backend/tests/contract/test_lens_contract.py`

**Test Coverage**:
- Schema CRUD operations
- Instance CRUD operations
- Lens resolution
- API endpoint contracts

---

## Usage Examples

### Example 1: Create a Mind Lens Instance

```python
from app.models.mind_lens import MindLensInstance
from app.services.lens.mind_lens_service import MindLensService

service = MindLensService()

instance = MindLensInstance(
    mind_lens_id="writer_001",
    schema_id="writer_schema_v1",
    owner_user_id="user_123",
    role="writer",
    label="Hemingway Style",
    description="Concise, direct writing style",
    values={
        "tone": "direct",
        "sentence_length": "short",
        "metaphor_usage": "minimal"
    }
)

created = service.create_instance(instance)
```

### Example 2: Resolve Lens for Execution

```python
from app.services.lens.mind_lens_service import MindLensService

service = MindLensService()

resolved = service.resolve_lens(
    user_id="user_123",
    workspace_id="workspace_001",
    playbook_id="content_drafting",
    role_hint="writer"
)

# Use resolved lens in execution context
execution_context.mind_lens = resolved.values
```

### Example 3: Use Lens in Execution Context

```python
from app.core.execution_context import ExecutionContext
from app.services.lens.mind_lens_service import MindLensService

service = MindLensService()

# Resolve lens
resolved = service.resolve_lens(
    user_id="user_123",
    workspace_id="workspace_001",
    role_hint="writer"
)

# Create execution context with lens
ctx = ExecutionContext(
    actor_id="user_123",
    workspace_id="workspace_001",
    mind_lens=resolved.values if resolved else None
)

# Use context in playbook execution
# Lens values will influence how the task is interpreted
```

---

## Integration with Execution Context

Mind Lens integrates with Execution Context through the `mind_lens` field:

**Location**: `backend/app/core/execution_context.py:26`

```python
class ExecutionContext(BaseModel):
    actor_id: str
    workspace_id: str
    tags: Optional[Dict[str, Any]] = None
    mind_lens: Optional[Dict[str, Any]] = None  # Resolved lens values
```

The `mind_lens` field contains resolved lens values that influence how tasks are interpreted and executed.

---

## Related Documentation

- [Execution Context Four-Layer Model](./execution-context-four-layer-model.md) - How Lens fits into the four-layer model
- [Lens Composition](./lens-composition.md) - Multi-lens combination (planned)
- [Execution Context](./execution-context.md) - Core ExecutionContext abstraction
- [System Overview](./system-overview.md) - Complete system architecture

---

**Last updated**: 2025-12-22

