# Long Chain Execution Architecture - Local Core

**Date**: 2025-12-05
**Version**: 1.0
**Scope**: mindscape-ai-local-core (Open Source Local Core)
**Status**: Implementation Complete

---

## Overview

This document describes the long chain execution architecture for Mindscape AI local core, based on the "Short Session + External State + Checkpoint/Resume" pattern, supporting long-running task execution, state recovery, and cross-engine collaboration.

### Core Principles

1. **Local First**: All core functionality must run completely locally
2. **External State**: Task state does not depend on a single conversation thread, but is stored in external memory
3. **Resumable Execution**: Support recovery from any checkpoint
4. **Modular Design**: Components are independent and collaborate through standard interfaces

---

## Architecture Components

### 1. Checkpoint/Resume Mechanism

#### 1.1 Design Goals

Support long-running tasks to save complete state at any point in time and resume execution from saved points.

#### 1.2 Core Components

**File**: `backend/app/services/playbook_checkpoint_manager.py`

**Main Class**: `PlaybookCheckpointManager`

**Key Methods**:
- `create_checkpoint()`: Create execution state snapshot
- `resume_from_checkpoint()`: Resume execution from snapshot
- `validate_checkpoint_data()`: Validate snapshot integrity

#### 1.3 Data Models

**ExecutionSession Extension** (`backend/app/models/workspace.py`):

```python
class ExecutionSession(BaseModel):
    # ... existing fields ...

    last_checkpoint: Optional[Dict[str, Any]] = Field(
        None,
        description="Last checkpoint data (JSON snapshot of execution state)"
    )
    phase_summaries: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Phase summaries written to external memory"
    )
    supports_resume: bool = Field(
        default=True,
        description="Whether this execution supports resume from checkpoint"
    )
```

**PlaybookExecution Model** (`backend/app/models/workspace.py`):

```python
class PlaybookExecution(BaseModel):
    id: str
    workspace_id: str
    playbook_code: str
    intent_instance_id: Optional[str]
    status: str  # running / paused / done / failed
    phase: Optional[str]
    last_checkpoint: Optional[str]  # JSON checkpoint data
    progress_log_path: Optional[str]
    feature_list_path: Optional[str]
    created_at: str
    updated_at: str
```

#### 1.4 Usage Example

```python
from backend.app.services.playbook_checkpoint_manager import PlaybookCheckpointManager

checkpoint_manager = PlaybookCheckpointManager(executions_store)

# Create checkpoint
checkpoint_id = checkpoint_manager.create_checkpoint(execution_session)

# Resume from checkpoint
resumed_session = checkpoint_manager.resume_from_checkpoint(execution_id)
```

---

### 2. Phase Summary Mechanism

#### 2.1 Design Goals

Automatically write summaries to external memory when phases complete, supporting context compression to avoid token limits.

#### 2.2 Core Components

**File**: `backend/app/services/playbook_phase_manager.py`

**Main Class**: `PlaybookPhaseManager`

**Key Methods**:
- `write_phase_summary()`: Write phase summary to MindEvent
- `load_phase_summaries()`: Load historical phase summaries
- `get_phase_context()`: Generate LLM context

#### 2.3 Event System

**MindEvent Extension** (`backend/app/models/mindscape.py`):

```python
class EventType(str, Enum):
    # ... existing event types ...
    PHASE_SUMMARY = "phase_summary"
```

**Phase Summary Event Structure**:

```python
{
    "execution_id": str,
    "phase_id": str,
    "summary": str,
    "artifacts": List[str],
    "intent_instance_id": Optional[str]
}
```

#### 2.4 Usage Example

```python
from backend.app.services.playbook_phase_manager import PlaybookPhaseManager

phase_manager = PlaybookPhaseManager(event_store, artifact_registry)

# Write phase summary
await phase_manager.write_phase_summary(
    execution_id="exec_123",
    phase_id="research",
    summary="Research completed successfully",
    artifacts=["artifact1", "artifact2"],
    workspace_id="ws_01"
)

# Load phase summaries as context
context = await phase_manager.get_phase_context(execution_id)
```

---

### 3. Initializer Agent Pattern

#### 3.1 Design Goals

Establish standardized execution environment and artifacts when executing a playbook for the first time.

#### 3.2 Core Components

**File**: `backend/app/services/playbook_initializer.py`

**Main Class**: `PlaybookInitializer`

**Key Methods**:
- `initialize_playbook_execution()`: Initialize playbook execution
- `get_bearings()`: Read existing state to determine next steps

#### 3.3 Initialization Flow

1. Create `playbook_feature_list.json` (feature list)
2. Create `playbook_progress.log` (progress log)
3. Create initial git commit (if needed)
4. Create PlaybookExecution record

#### 3.4 Usage Example

```python
from backend.app.services.playbook_initializer import PlaybookInitializer

initializer = PlaybookInitializer(executions_store, artifact_registry)

# Initialize execution
init_result = await initializer.initialize_playbook_execution(
    execution_id="exec_123",
    playbook_code="pdf_ocr_processing",
    workspace_id="ws_01"
)

# Read existing state
bearings = await initializer.get_bearings(execution_id)
```

---

### 4. Task IR + Handoff Mechanism (Local Core)

#### 4.1 Design Goals

Provide unified task description format (Task IR), supporting seamless handoff between local engines (Playbook, MCP).

#### 4.2 Core Components

**Task IR Schema** (`backend/app/models/task_ir.py`):

```python
class TaskIR(BaseModel):
    task_id: str
    intent_instance_id: str
    workspace_id: str
    actor_id: str
    current_phase: Optional[str]
    status: TaskStatus
    phases: List[PhaseIR]
    artifacts: List[ArtifactReference]
    metadata: ExecutionMetadata
    created_at: str
    updated_at: str
    last_checkpoint_at: Optional[str]
```

**Artifact Registry** (`backend/app/services/artifact_registry.py`):

```python
class ArtifactRegistry:
    def __init__(self, storage_backend: str = "filesystem"):
        self.storage_backend = storage_backend  # filesystem / s3 / weaviate

    async def register_artifact(
        self,
        artifact: ArtifactReference,
        content: Any
    ) -> str

    async def load_artifact_content(self, artifact_id: str) -> Any
    async def list_artifacts(
        self,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[ArtifactReference]
```

**Handoff Handler** (`backend/app/services/handoff_handler.py`):

```python
class HandoffHandler:
    async def handle_handoff(self, handoff_event: HandoffEvent) -> Dict[str, Any]
    async def initiate_task_execution(
        self,
        task_ir: TaskIR,
        starting_engine: str
    ) -> Dict[str, Any]
```

#### 4.3 Local Engine Support

**Implemented**:
- Playbook Engine ↔ Task IR
- MCP Tools ↔ Task IR (interface reserved)

**IR Adapters**:
- `PlaybookIRAdapter`: Task IR ↔ Playbook format translation
- `MCPIRAdapter`: Task IR ↔ MCP format translation (reserved)

#### 4.4 Usage Example

```python
from backend.app.models.task_ir import TaskIR, PhaseIR
from backend.app.services.handoff_handler import HandoffHandler

# Create Task IR
task_ir = TaskIR(
    task_id="task_001",
    intent_instance_id="intent_456",
    workspace_id="ws_01",
    actor_id="user_alice",
    phases=[
        PhaseIR(
            id="research",
            name="Research Phase",
            preferred_engine="playbook:research_playbook",
            status="pending"
        )
    ]
)

# Handle handoff
handoff_handler = HandoffHandler(task_ir_store, artifact_registry)
result = await handoff_handler.handle_handoff(handoff_event)
```

---

### 5. Database Schema

#### 5.1 Playbook Executions Table

**File**: `backend/app/services/stores/schema.py`

```sql
CREATE TABLE IF NOT EXISTS playbook_executions (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    playbook_code TEXT NOT NULL,
    intent_instance_id TEXT,
    status TEXT NOT NULL,
    phase TEXT,
    last_checkpoint TEXT,
    progress_log_path TEXT,
    feature_list_path TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (workspace_id) REFERENCES workspaces (id)
);

CREATE INDEX idx_playbook_executions_workspace ON playbook_executions(workspace_id);
CREATE INDEX idx_playbook_executions_status ON playbook_executions(status);
CREATE INDEX idx_playbook_executions_intent ON playbook_executions(intent_instance_id);
```

#### 5.2 Task IR Store

**File**: `backend/app/services/stores/task_ir_store.py`

Task IR data is stored in the `playbook_executions` table, with Task IR data in JSON format stored in the `last_checkpoint` field.

---

### 6. Executor Integration

#### 6.1 PlaybookRunExecutor Integration

**File**: `backend/app/services/playbook_run_executor.py`

**Integration Points**:
- Create PlaybookExecution record during initialization
- Use PlaybookInitializer for artifact initialization
- Create checkpoints periodically
- Write phase summary when phases complete
- Support recovery from checkpoint on errors

#### 6.2 Execution Flow

```
1. Initialization Phase
   ├── PlaybookInitializer.initialize_playbook_execution()
   ├── Create PlaybookExecution record
   └── Create initial artifacts

2. Execution Phase
   ├── Execute playbook steps
   ├── Create checkpoints periodically
   └── Write phase summary when phases complete

3. Recovery Phase (if needed)
   ├── PlaybookCheckpointManager.resume_from_checkpoint()
   ├── Restore execution state
   └── Continue execution
```

---

## Local Storage Backend

### Filesystem Storage Backend

**Default Backend**: `filesystem`

**Storage Locations**:
- Artifacts: `{workspace_storage_path}/artifacts/`
- Checkpoints: Stored in database `playbook_executions.last_checkpoint`
- Phase Summaries: Stored through MindEvent system

**Configuration**:

```python
artifact_registry = ArtifactRegistry(storage_backend="filesystem")
```

---

## Local Limitations and Considerations

### 1. Storage Space

- Local filesystem storage space is limited
- Recommend periodic cleanup of old artifacts
- Checkpoint data may be large, consider compression

### 2. Execution Time

- Local execution is limited by hardware resources
- Long-running tasks recommend using Cloud Runtime (see Cloud documentation)

### 3. Concurrent Execution

- Local execution supports limited concurrency
- Recommend using job queue to manage execution order

---

## Backward Compatibility

### Legacy Execution Compatibility

- Legacy executions without checkpoints continue to work normally
- `supports_resume` defaults to `True`, but legacy executions may be `False`
- Phase summaries are optional and do not affect basic functionality

### Data Migration

If you need to convert existing Tasks to PlaybookExecution, refer to migration scripts (if available).

---

## Related Files

### Core Models
- `backend/app/models/workspace.py` - ExecutionSession, PlaybookExecution
- `backend/app/models/task_ir.py` - TaskIR, PhaseIR, ArtifactReference
- `backend/app/models/execution_metadata.py` - ExecutionMetadata
- `backend/app/models/mindscape.py` - MindEvent, EventType

### Service Layer
- `backend/app/services/playbook_checkpoint_manager.py` - Checkpoint management
- `backend/app/services/playbook_phase_manager.py` - Phase Summary management
- `backend/app/services/playbook_initializer.py` - Initialization management
- `backend/app/services/artifact_registry.py` - Artifact management
- `backend/app/services/handoff_handler.py` - Handoff handling
- `backend/app/services/playbook_ir_adapter.py` - Playbook IR translation
- `backend/app/services/playbook_run_executor.py` - Executor integration

### Data Access
- `backend/app/services/stores/playbook_executions_store.py` - PlaybookExecution Store
- `backend/app/services/stores/task_ir_store.py` - Task IR Store
- `backend/app/services/stores/schema.py` - Database Schema

---

## Verification and Testing

### Functionality Verification Checklist

- [x] Checkpoint mechanism correctly saves execution state
- [x] Resume mechanism correctly restores execution
- [x] Phase Summary correctly writes to external memory
- [x] Initializer correctly creates initialization files
- [x] Task IR correctly describes task state
- [x] Artifact Registry correctly manages artifacts
- [x] Handoff correctly handles handoff between local engines

### Test Examples

See unit tests and integration tests for each service.

---

**Last Updated**: 2025-12-05
**Maintainer**: Mindscape AI Development Team
**Related Documentation**:
