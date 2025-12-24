# Lens Composition Core Architecture

Lens Composition represents multi-lens combination recipes. It is a composition layer on top of Mind Lens instances, not a replacement layer.

**Last updated**: 2025-12-22

---

## Overview

Lens Composition allows multiple Mind Lens instances to be combined into a single execution context. This enables complex scenarios where different perspectives need to work together, such as combining a writer's style with a designer's visual sense.

**Key Characteristics**:
- Composition layer on top of Mind Lens instances
- References existing MindLensInstance, does not redefine Lens
- Supports multiple fusion strategies
- Can be weighted, prioritized, and scoped

---

## Core Models

### LensComposition

Multi-lens combination recipe.

**Location**: `backend/app/models/lens_composition.py:52-89`

```python
class LensComposition(BaseModel):
    composition_id: str
    workspace_id: str
    name: str
    description: Optional[str] = None
    lens_stack: List[LensReference]
    fusion_strategy: str = "priority_then_weighted"
    metadata: Optional[Dict] = None
    created_at: datetime
    updated_at: datetime
```

**Fields**:
- `composition_id`: Unique composition identifier
- `workspace_id`: Workspace ID
- `name`: Composition name
- `description`: Optional description
- `lens_stack`: Ordered list of lens references
- `fusion_strategy`: Fusion strategy (priority | weighted | priority_then_weighted)
- `metadata`: Additional metadata

**Helper Methods**:
- `get_lenses_by_modality(modality: LensModality) -> List[LensReference]`: Filter lenses by modality
- `get_lenses_by_role(role: LensRole) -> List[LensReference]`: Filter lenses by role
- `get_lenses_by_scope(scope: str) -> List[LensReference]`: Filter lenses by scope
- `get_total_weight() -> float`: Calculate total weight

### LensReference

Lens reference in composition.

**Location**: `backend/app/models/lens_composition.py:34-50`

```python
class LensReference(BaseModel):
    lens_instance_id: str
    role: LensRole
    modality: LensModality
    weight: float = 1.0
    priority: int = 0
    scope: List[str] = ["all"]
    locked: bool = False
```

**Fields**:
- `lens_instance_id`: Reference to MindLensInstance.mind_lens_id
- `role`: Professional role for composition logic
- `modality`: Modality type (visual, audio, text, brand)
- `weight`: Weight (0-1) for weighted fusion
- `priority`: Priority (higher number = higher priority)
- `scope`: Application scope (e.g., ["all"], ["step_1", "step_2"])
- `locked`: Whether locked (cannot be overridden)

### FusedLensContext

Fused lens context after fusion.

**Location**: `backend/app/models/lens_composition.py:91-99`

```python
class FusedLensContext(BaseModel):
    composition_id: str
    fused_values: Dict
    source_lenses: List[str]
    fusion_log: List[Dict]
    fusion_strategy: str
    applied_at: datetime
```

**Fields**:
- `composition_id`: Source Composition ID
- `fused_values`: Fused dimension values
- `source_lenses`: Source Lens IDs
- `fusion_log`: Fusion operation log
- `fusion_strategy`: Fusion strategy used

### Enums

**LensRole**: Professional role type
- `DESIGNER`, `ARTIST`, `DIRECTOR`, `VOICE_ACTOR`, `MUSICIAN`, `WRITER`, `SCREENWRITER`, `JOURNALIST`, `BRAND`, `MARKETER`

**LensModality**: Modality type
- `VISUAL`, `AUDIO`, `TEXT`, `BRAND`

**Location**: `backend/app/models/lens_composition.py:12-32`

---

## Core Services

### CompositionService

Service for managing Lens Compositions.

**Location**: `backend/app/services/lens/composition_service.py`

**Key Methods**:

- `create_composition(composition: LensComposition) -> LensComposition`: Create a new composition
- `get_composition(composition_id: str) -> Optional[LensComposition]`: Get composition by ID
- `update_composition(composition_id: str, updates: dict) -> Optional[LensComposition]`: Update composition
- `delete_composition(composition_id: str) -> bool`: Delete composition
- `list_compositions(workspace_id: Optional[str], limit: int) -> List[LensComposition]`: List compositions

**Code Reference**: `backend/app/services/lens/composition_service.py:13-104`

### FusionService

Service for fusing multiple lenses.

**Location**: `backend/app/services/lens/fusion_service.py`

**Key Methods**:

- `fuse_composition(composition: LensComposition, lens_instances: Dict[str, MindLensInstance]) -> FusedLensContext`: Fuse a composition into a single lens context

**Fusion Strategies**:

1. **priority**: Highest priority lens wins
2. **weighted**: Weighted average of all lenses
3. **priority_then_weighted**: Priority first, then weighted average for same priority (default)

**Code Reference**: `backend/app/services/lens/fusion_service.py:16-165`

---

## API Routes

### Base Path

`/api/v1/compositions`

**Location**: `backend/app/routes/core/composition.py`

### Endpoints

#### POST `/api/v1/compositions`

Create a new composition.

**Request Body**: `LensComposition`

**Response**: `LensComposition` (201 Created)

**Code Reference**: `backend/app/routes/core/composition.py:25-37`

#### GET `/api/v1/compositions/{composition_id}`

Get composition by ID.

**Response**: `LensComposition`

**Code Reference**: `backend/app/routes/core/composition.py:40-50`

#### PUT `/api/v1/compositions/{composition_id}`

Update composition.

**Request Body**: `Dict[str, Any]` (update fields)

**Response**: `LensComposition`

**Code Reference**: `backend/app/routes/core/composition.py:53-66`

#### DELETE `/api/v1/compositions/{composition_id}`

Delete composition.

**Response**: 204 No Content

**Code Reference**: `backend/app/routes/core/composition.py:69-77`

#### GET `/api/v1/compositions`

List compositions.

**Query Parameters**:
- `workspace_id` (optional): Filter by workspace ID
- `limit` (default: 50): Maximum number of results

**Response**: `List[LensComposition]`

**Code Reference**: `backend/app/routes/core/composition.py:80-90`

#### POST `/api/v1/compositions/{composition_id}/fuse`

Fuse composition into a single lens context.

**Request Body**: `FuseRequest`
```python
{
    "composition_id": str,
    "lens_instances": Dict[str, Dict[str, Any]]
}
```

**Response**: `FusedLensContext`

**Code Reference**: `backend/app/routes/core/composition.py:93-118`

---

## Fusion Strategies

### Priority Fusion

Highest priority lens wins. If multiple lenses have the same highest priority, falls back to weighted fusion.

**Code Reference**: `backend/app/services/lens/fusion_service.py:46-82`

### Weighted Fusion

Weighted average of all lenses. Numeric values are averaged by weight, strings use the first value.

**Code Reference**: `backend/app/services/lens/fusion_service.py:84-94`

### Priority Then Weighted Fusion (Default)

Priority first, then weighted average for lenses with the same priority.

**Code Reference**: `backend/app/services/lens/fusion_service.py:96-114`

---

## Usage Examples

### Example 1: Create a Composition

```python
from app.models.lens_composition import (
    LensComposition,
    LensReference,
    LensRole,
    LensModality
)

composition = LensComposition(
    composition_id="comp_001",
    workspace_id="workspace_001",
    name="Writer + Designer",
    description="Combines writer's style with designer's visual sense",
    lens_stack=[
        LensReference(
            lens_instance_id="writer_001",
            role=LensRole.WRITER,
            modality=LensModality.TEXT,
            weight=0.6,
            priority=1
        ),
        LensReference(
            lens_instance_id="designer_001",
            role=LensRole.DESIGNER,
            modality=LensModality.VISUAL,
            weight=0.4,
            priority=1
        )
    ],
    fusion_strategy="priority_then_weighted"
)

service = CompositionService()
created = service.create_composition(composition)
```

### Example 2: Fuse a Composition

```python
from app.services.lens.composition_service import CompositionService
from app.services.lens.fusion_service import FusionService
from app.models.mind_lens import MindLensInstance

composition_service = CompositionService()
fusion_service = FusionService()

# Get composition
composition = composition_service.get_composition("comp_001")

# Get lens instances
lens_instances = {
    "writer_001": MindLensInstance(...),
    "designer_001": MindLensInstance(...)
}

# Fuse composition
fused = fusion_service.fuse_composition(composition, lens_instances)

# Use fused context in execution
execution_context.mind_lens = fused.fused_values
```

### Example 3: Filter Lenses by Scope

```python
from app.models.lens_composition import LensComposition

composition = composition_service.get_composition("comp_001")

# Get lenses for specific step
step_lenses = composition.get_lenses_by_scope("step_1")

# Get lenses for specific modality
text_lenses = composition.get_lenses_by_modality(LensModality.TEXT)

# Get lenses for specific role
writer_lenses = composition.get_lenses_by_role(LensRole.WRITER)
```

### Example 4: Use Fused Context in Execution

```python
from app.core.execution_context import ExecutionContext
from app.services.lens.composition_service import CompositionService
from app.services.lens.fusion_service import FusionService

composition_service = CompositionService()
fusion_service = FusionService()

# Get and fuse composition
composition = composition_service.get_composition("comp_001")
fused = fusion_service.fuse_composition(composition, lens_instances)

# Create execution context with fused lens
ctx = ExecutionContext(
    actor_id="user_123",
    workspace_id="workspace_001",
    mind_lens=fused.fused_values
)

# Use context in playbook execution
# Fused lens values influence how the task is interpreted
```

---

## Integration with Mind Lens

Lens Composition references existing MindLensInstance objects:

- Composition does not redefine Lens
- Composition references `MindLensInstance.mind_lens_id`
- Multiple compositions can reference the same lens instance
- Lens instances can be shared across compositions

---

## Related Documentation

- [Mind Lens](./mind-lens.md) - Mind Lens core architecture
- [Execution Context Four-Layer Model](./execution-context-four-layer-model.md) - How Lens fits into the four-layer model
- [Execution Context](./execution-context.md) - Core ExecutionContext abstraction
- [System Overview](./system-overview.md) - Complete system architecture

---

**Last updated**: 2025-12-22


