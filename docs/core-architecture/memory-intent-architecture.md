# Mindscape AI: Event, Intent Governance, and Memory Architecture

> This document describes the three-layer design of Mindscape AI (shared by local workstation and Cloud) for "Event Recording → Intent Governance → Memory/Embedding", providing technical implementation details for developers.

**Last Updated**: 2025-12-01
**Status**: ✅ Fully Aligned with Current Implementation

**Architecture Version**: v0.6.2 (Post-Refactoring)
**Database Schema Version**: Includes workspace_id migration, habit learning, entity/tag system

---

## Table of Contents

1. [Why Three Layers?](#1-why-three-layers)
2. [Event Layer](#2-event-layer)
3. [Intent Governance Layer](#3-intent-governance-layer)
4. [Memory/Embedding Layer](#4-memoryembedding-layer)
5. [Data Models and Schema](#5-data-models-and-schema)
6. [Typical Data Flow](#6-typical-data-flow)
7. [Implementation Details](#7-implementation-details)

---

## 1. Why Three Layers?

If we blindly dump all user behaviors into embedding, long-term memory, or intent analysis:

- **Costs would be very high** (tokens / storage space)
- **Signals would become noisy**, drowning out truly important information
- **Users would struggle to understand** what the system actually remembers

Therefore, Mindscape AI uses a three-layer approach:

1. **Event Layer**: Records almost everything, only responsible for "what happened"
2. **Intent Layer**: Only processes "semantic requests"
3. **Memory Layer**: Only stores "worth-preserving outcomes and preferences" long-term

---

## 2. Event Layer

### 2.1 Design Principles

The event layer records **"what just happened"** for:

- Debugging and troubleshooting
- Usage statistics and analytics (which capability packs / playbooks are frequently used)
- High-level features (e.g., detecting if a new role should be created)

### 2.2 Event Types (EventType)

```python
class EventType(str, Enum):
    MESSAGE = "message"                    # Conversation messages (user/assistant)
    TOOL_CALL = "tool_call"                # Tool/function calls
    PLAYBOOK_STEP = "playbook_step"        # Playbook execution steps
    INSIGHT = "insight"                   # Generated insights or observations
    HABIT_OBSERVATION = "habit_observation" # Habit learning observations
    PROJECT_CREATED = "project_created"   # Project creation events
    PROJECT_UPDATED = "project_updated"     # Project update events
    INTENT_CREATED = "intent_created"      # Intent creation events
    INTENT_UPDATED = "intent_updated"       # Intent update events
    AGENT_EXECUTION = "agent_execution"    # Agent execution events
    OBSIDIAN_NOTE_UPDATED = "obsidian_note_updated"  # Obsidian note creation/update events
```

**Implementation Reference**: `backend/app/models/mindscape.py:275-287`

### 2.3 Event Model (MindEvent)

```python
class MindEvent(BaseModel):
    """
    Mindspace event for timeline reconstruction

    All events that happen in the mindspace are recorded here,
    allowing replay and recombination for features like:
    - Annual book generation
    - Project proposal compilation
    - Habit learning analysis
    """
    id: str                                  # UUID
    timestamp: datetime                       # UTC timestamp
    actor: EventActor                        # Who/what triggered this (USER / ASSISTANT / SYSTEM)
    channel: str                             # Source channel ("local_chat" / "line" / "wp" / "playbook" / "api")
    profile_id: str                          # User profile ID
    project_id: Optional[str]               # Project ID (if applicable)
    workspace_id: Optional[str]              # Workspace ID (if applicable) - Added in migration
    event_type: EventType                    # Event type (11 types)
    payload: Dict[str, Any]                  # Event-specific content (flexible JSON)
    entity_ids: List[str]                    # Related entity IDs (e.g., project_id, intent_id)
    metadata: Dict[str, Any]                 # Metadata for controlling behavior (should_embed, is_final, etc.)
```

**Implementation Reference**: `backend/app/models/mindscape.py:297-323`

### 2.4 Event Payload Examples

#### MESSAGE Event

```json
{
  "execution_id": "exec_123",
  "playbook_code": "major_proposal",
  "message": "Help me write a government grant proposal",
  "role": "user"
}
```

#### PLAYBOOK_STEP Event

```json
{
  "execution_id": "exec_123",
  "playbook_code": "major_proposal",
  "step": "continue",
  "is_complete": true,
  "is_final_output": true,
  "conversation_length": 15
}
```

#### INTENT_CREATED Event

```json
{
  "intent_id": "intent_456",
  "title": "2025 Annual Book Project",
  "description": "Compile this year's learning into a book",
  "status": "active",
  "priority": "high"
}
```

### 2.5 Metadata Fields

Metadata controls subsequent event processing behavior:

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `should_embed` | `bool` | Whether to generate embedding | `true` (when `is_final=True`) |
| `is_final` | `bool` | Whether this is final output | `true` (when playbook completes) |
| `is_artifact` | `bool` | Whether this is a stable artifact | `true` (when proposal draft completes) |
| `has_structured_output` | `bool` | Whether structured output exists | `true` (when playbook has JSON output) |
| `from_completed_playbook` | `bool` | Whether from completed playbook | `true` |
| `artifact_type` | `str` | Artifact type | `"proposal"`, `"storyboard"` |
| `locale` | `str` | Language setting | `"en"`, `"zh-TW"` |

### 2.6 What Gets Recorded as Events

- **Conversations**: User messages, AI replies, Workspace sessions
- **Tasks and Playbooks**: Execution steps, success/failure status
- **Capability Packs and Roles**: Installation/updates/removal, role creation/modification
- **Files and Content**: Upload/update/delete, import/export
- **System Operations**: Health checks, API key test results
- **Tool Calls**: Tool/function execution events
- **Insights**: Generated insights or observations
- **Habit Observations**: User behavior patterns (for habit learning)
- **Project Events**: Project creation and updates
- **Agent Executions**: AI agent execution events
- **Obsidian Notes**: Obsidian note creation/update events

> **Not recorded**: Pure UI actions (mouse movements, visual animations), unless they have clear semantic meaning for task flow.

**Default Behavior**: Events are recorded with `generate_embedding=False` (opt-in, not opt-out). Only events that meet `should_generate_embedding()` criteria will generate embeddings.

**Implementation Reference**: `backend/app/services/stores/events_store.py:18-74`

---

## 3. Intent Governance Layer

### 3.1 Design Principles

Intent governance answers: **"What type of task is this request?"**

### 3.2 What Enters Intent Governance

**Enters Intent:**

- Natural language requests from users to AI
- Conversations with roles in Workspace (text)

**Usually doesn't enter Intent:**

- Pure UI operations (expand/collapse, mouse movements)
- Pure setting changes (theme switching, window adjustments)
- Low-level technical events (health checks, scheduled tasks)

> Simply put: **Only behaviors that "require AI to make semantic responses or decisions" go through intent governance.**

### 3.3 Intent Analysis Output

Typical output includes:

```python
{
  "intent_type": "write_proposal",      # Task type
  "topic": "government_grant",           # Domain/Topic
  "suggested_playbook": "major_proposal.playbook_v1",  # Suggested playbook
  "suggested_role": "proposal_coach",   # Suggested role
  "required_tools": ["major_proposal.assemble"],  # Required tools
  "needs_clarification": True,          # Whether clarification needed
  "clarification_questions": [...]      # Clarification questions
}
```

### 3.4 Implementation Architecture

The Intent Pipeline uses a **3-layer analysis approach**:

**Layer 1: Interaction Type** (Rule-based + small model)
- Classifies: QA, START_PLAYBOOK, MANAGE_SETTINGS, UNKNOWN
- Fast path using pattern matching

**Layer 2: Task Domain** (Intent cards / few-shot / embedding similarity)
- Classifies: PROPOSAL_WRITING, YEARLY_REVIEW, HABIT_LEARNING, PROJECT_PLANNING, CONTENT_WRITING
- Uses intent cards and few-shot examples

**Layer 3: Playbook Selection + Context Preparation**
- Selects appropriate playbook
- Prepares context for execution

```python
class IntentPipeline:
    def __init__(self):
        self.analyzer = IntentAnalyzer()
        self.rule_matcher = RuleBasedIntentMatcher()
        self.llm_matcher = LLMBasedIntentMatcher()

    async def analyze(self, message: str, context: Dict) -> IntentAnalysisResult:
        # Layer 1: Interaction Type
        interaction_type = self.rule_matcher.match(message)

        # Layer 2: Task Domain (if playbook needed)
        if interaction_type == InteractionType.START_PLAYBOOK:
            task_domain = await self.analyzer.classify_task_domain(message, context)

        # Layer 3: Playbook Selection
        if task_domain:
            playbook = await self.analyzer.select_playbook(task_domain, context)

        return IntentAnalysisResult(...)
```

**Intent Logs**: All intent analysis results are logged to `intent_logs` table for audit and learning.

**Implementation Reference**: `backend/app/services/intent_analyzer.py:1-817`

---

## 4. Memory/Embedding Layer

### 4.1 Design Principles

The memory layer answers: **"What content is worth preserving long-term and can be queried or referenced in the future?"**

### 4.2 Knowledge/Content Memory (Embeddings)

The following content "may" be vectorized and written to the knowledge base:

- **Stable Documents and Artifacts**:
  - Completed proposal drafts (v1 / v2 / Final)
  - Organized storyboard scripts
  - Annual compilation/review chapter content

- **Important Files**:
  - Files explicitly uploaded and marked as "for future query" (PDF / Word / notes)
  - Articles and documentation from WordPress / Notion / other systems

- **Deep Discussions**:
  - Long-form analysis results on specific topics that have been organized

The following content **usually does NOT get vectorized directly**:

- Casual chat, fragmented conversations
- Every minor text adjustment
- Pure UI operation events
- Short-term, one-time temporary questions

### 4.3 Personal Preferences and Long-term Projects (Mindscape Store)

Another part is memory about **"you as a person"**:

- **Long-term Projects**:
  - Examples: "2025 Annual: Publish a book each year", "Startup proposal series"
  - Exist as "project cards" or "Mindscape nodes"
  - Stored in `intents` table with status and priority

- **Preference Settings**:
  - Writing style (formal / casual / concise / detailed)
  - Language preferences, formatting habits
  - Stored in `profiles.preferences` (JSON)

- **Habit Learning** (Automatic):
  - System observes user behavior patterns
  - Generates habit candidates (e.g., "prefers zh-TW", "uses casual tone")
  - User confirms/rejects habits
  - Confirmed habits automatically applied to profile preferences
  - Stored in `habit_observations`, `habit_candidates`, `habit_audit_logs` tables

**Implementation Reference**:
- Habit models: `backend/app/models/habit.py`
- Habit store: `backend/app/services/habit_store.py`
- Profile integration: `backend/app/services/mindscape_store.py:114-185`

### 4.4 Embedding Generation Logic (Selective Strategy)

**Key Principle**: Only generate embeddings for stable artifacts, not transient content.

```python
class EventEmbeddingGenerator:
    def should_generate_embedding(self, event: MindEvent) -> bool:
        """
        Determine if an event should generate embedding

        Only generates embeddings for:
        - Stable artifacts (finished products, completed intents)
        - User-explicit saves (metadata flag)
        - Deep discussions on specific topics (playbook outputs)

        Does NOT generate for:
        - Every chat message
        - Minor edits/cursor movements
        - All request/response pairs
        - UI actions/settings changes
        """
        # Check metadata flags (highest priority)
        if event.metadata and isinstance(event.metadata, dict):
            if event.metadata.get("should_embed") is True:
                return True
            if event.metadata.get("is_final") is True:
                return True
            if event.metadata.get("is_artifact") is True:
                return True

        # Check event type and status
        if event.event_type == EventType.INTENT_CREATED or event.event_type == EventType.INTENT_UPDATED:
            # Only embed completed or high-priority intents
            if event.payload and isinstance(event.payload, dict):
                status = event.payload.get("status")
                priority = event.payload.get("priority")
                if status == "completed" or priority in ["high", "critical"]:
                    return True

        if event.event_type == EventType.PLAYBOOK_STEP:
            # Only embed final outputs, not intermediate steps
            if event.payload and isinstance(event.payload, dict):
                if event.payload.get("is_final_output") is True:
                    return True
                if event.payload.get("step_type") == "output" and event.payload.get("status") == "completed":
                    return True

        if event.event_type == EventType.MESSAGE:
            # Only embed if explicitly marked or from completed playbook
            if event.metadata and isinstance(event.metadata, dict):
                if event.metadata.get("from_completed_playbook") is True:
                    return True
                if event.metadata.get("is_artifact_output") is True:
                    return True

        if event.event_type == EventType.OBSIDIAN_NOTE_UPDATED:
            # Only embed research-related notes based on metadata filters
            if event.metadata and isinstance(event.metadata, dict):
                should_embed = event.metadata.get("should_embed", False)
                if should_embed:
                    return True

        # Default: don't generate embedding
        return False
```

**Implementation Reference**: `backend/app/services/event_embedding_generator.py:34-91`

### 4.5 Trigger Conditions

In practice, the system determines whether to generate embeddings through:

- **Playbook Completion**: When a playbook marks a version as "draft complete" → send content to vector database
- **User Explicit Action**: User clicks "Save to Knowledge Base" button
- **Command Trigger**: User commands in Workspace: "Save this to knowledge base"
- **Intent Completion**: When Intent status becomes `COMPLETED` and priority is `high` or `critical`

---

## 5. Data Models and Schema

### 5.1 Complete MindEvent Schema

```python
class MindEvent(BaseModel):
    id: str = Field(..., description="Unique event identifier (UUID)")
    timestamp: datetime = Field(..., description="Event timestamp (UTC)")
    actor: EventActor = Field(..., description="Who/what triggered this event")
    channel: str = Field(..., description="Source channel: 'playbook' | 'api' | 'capability'")
    profile_id: str = Field(..., description="User profile ID")
    project_id: Optional[str] = Field(None, description="Related project ID")
    workspace_id: Optional[str] = Field(None, description="Related workspace ID")
    event_type: EventType = Field(..., description="Type of event")
    payload: Dict[str, Any] = Field(..., description="Event-specific payload")
    entity_ids: List[str] = Field(default_factory=list, description="Related entity IDs")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata for controlling behavior")
```

### 5.2 EventActor Enumeration

```python
class EventActor(str, Enum):
    USER = "user"           # User-triggered
    ASSISTANT = "assistant"  # AI assistant-triggered
    SYSTEM = "system"       # System auto-triggered
```

### 5.3 Database Table Structure

#### mind_events Table (SQLite)

**Note**: Events are stored in SQLite database (`mindscape.db`), not PostgreSQL.

```sql
CREATE TABLE IF NOT EXISTS mind_events (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    actor TEXT NOT NULL,
    channel TEXT NOT NULL,
    profile_id TEXT NOT NULL,
    project_id TEXT,
    workspace_id TEXT,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,  -- JSON
    entity_ids TEXT,        -- JSON array
    metadata TEXT,          -- JSON
    FOREIGN KEY (profile_id) REFERENCES profiles (id),
    FOREIGN KEY (workspace_id) REFERENCES workspaces (id)
);

CREATE INDEX idx_mind_events_profile ON mind_events(profile_id);
CREATE INDEX idx_mind_events_project ON mind_events(project_id);
CREATE INDEX idx_mind_events_type ON mind_events(event_type);
CREATE INDEX idx_mind_events_timestamp ON mind_events(timestamp DESC);
CREATE INDEX idx_mind_events_profile_timestamp ON mind_events(profile_id, timestamp DESC);
CREATE INDEX idx_mind_events_workspace ON mind_events(workspace_id);
CREATE INDEX idx_mind_events_workspace_timestamp ON mind_events(workspace_id, timestamp DESC);
```

**Implementation Reference**: `backend/app/services/stores/schema.py:172-200`

#### intent_logs Table (SQLite)

**Note**: Intent governance logs are stored in SQLite database (`mindscape.db`).

```sql
CREATE TABLE IF NOT EXISTS intent_logs (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    raw_input TEXT NOT NULL,
    channel TEXT NOT NULL,
    profile_id TEXT NOT NULL,
    project_id TEXT,
    workspace_id TEXT,
    pipeline_steps TEXT NOT NULL,  -- JSON: Layer 1, 2, 3 results
    final_decision TEXT NOT NULL,  -- JSON: Selected playbook/action
    user_override TEXT,            -- User manual override (if any)
    metadata TEXT,                 -- JSON
    FOREIGN KEY (profile_id) REFERENCES profiles (id),
    FOREIGN KEY (workspace_id) REFERENCES workspaces (id)
);

CREATE INDEX idx_intent_logs_profile ON intent_logs(profile_id);
CREATE INDEX idx_intent_logs_timestamp ON intent_logs(timestamp DESC);
CREATE INDEX idx_intent_logs_profile_timestamp ON intent_logs(profile_id, timestamp DESC);
CREATE INDEX idx_intent_logs_has_override ON intent_logs(user_override) WHERE user_override IS NOT NULL;
CREATE INDEX idx_intent_logs_workspace ON intent_logs(workspace_id);
CREATE INDEX idx_intent_logs_workspace_timestamp ON intent_logs(workspace_id, timestamp DESC);
```

**Implementation Reference**: `backend/app/services/stores/schema.py:203-233`

#### workspaces Table (SQLite)

```sql
CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    primary_project_id TEXT,
    default_playbook_id TEXT,
    default_locale TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (owner_user_id) REFERENCES profiles (id)
);

CREATE INDEX idx_workspaces_owner ON workspaces(owner_user_id);
CREATE INDEX idx_workspaces_project ON workspaces(primary_project_id);
```

**Implementation Reference**: `backend/app/services/stores/schema.py:149-166`

#### habit_observations, habit_candidates, habit_audit_logs Tables (SQLite)

**Habit Learning System** - Tracks user behavior patterns and learns preferences:

```sql
-- Habit observations (raw behavior data)
CREATE TABLE IF NOT EXISTS habit_observations (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL,
    habit_key TEXT NOT NULL,
    habit_value TEXT NOT NULL,
    habit_category TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_id TEXT,
    source_context TEXT,
    observed_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (profile_id) REFERENCES profiles (id)
);

-- Habit candidates (aggregated patterns)
CREATE TABLE IF NOT EXISTS habit_candidates (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL,
    habit_key TEXT NOT NULL,
    habit_value TEXT NOT NULL,
    habit_category TEXT NOT NULL,
    evidence_count INTEGER DEFAULT 0,
    confidence REAL DEFAULT 0.0,
    first_seen_at TEXT,
    last_seen_at TEXT,
    evidence_refs TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (profile_id) REFERENCES profiles (id),
    UNIQUE(profile_id, habit_key, habit_value)
);

-- Habit audit logs (change tracking)
CREATE TABLE IF NOT EXISTS habit_audit_logs (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    action TEXT NOT NULL,
    previous_status TEXT,
    new_status TEXT,
    actor_type TEXT DEFAULT 'system',
    actor_id TEXT,
    reason TEXT,
    metadata TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (profile_id) REFERENCES profiles (id),
    FOREIGN KEY (candidate_id) REFERENCES habit_candidates (id)
);
```

**Implementation Reference**: `backend/app/services/stores/schema.py:78-146`, `backend/app/models/habit.py`

#### entities, tags, entity_tags Tables (SQLite)

**Entity and Tag System** - For organizing and categorizing content:

```sql
CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    name TEXT NOT NULL,
    profile_id TEXT NOT NULL,
    description TEXT,
    metadata TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (profile_id) REFERENCES profiles (id)
);

CREATE TABLE IF NOT EXISTS tags (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    profile_id TEXT NOT NULL,
    description TEXT,
    color TEXT,
    metadata TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (profile_id) REFERENCES profiles (id)
);

CREATE TABLE IF NOT EXISTS entity_tags (
    entity_id TEXT NOT NULL,
    tag_id TEXT NOT NULL,
    value TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (entity_id, tag_id),
    FOREIGN KEY (entity_id) REFERENCES entities (id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags (id) ON DELETE CASCADE
);
```

**Implementation Reference**: `backend/app/services/stores/schema.py:236-293`

#### mindscape_personal Table (PostgreSQL + pgvector)

**Note**: Embeddings are stored in PostgreSQL with pgvector extension, not SQLite.

```sql
CREATE TABLE IF NOT EXISTS mindscape_personal (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL DEFAULT 'default_user',

    -- Content source
    source_type TEXT NOT NULL,  -- 'self_profile' / 'intent' / 'task' / 'weekly_review' / 'daily_journal' / 'reflection'
    content TEXT NOT NULL,
    metadata JSONB,

    -- Source information (for compatibility)
    source_id TEXT,
    source_context TEXT,

    -- Confidence and weight
    confidence REAL DEFAULT 0.5,
    weight REAL DEFAULT 1.0,

    -- Vector embedding (pgvector)
    embedding vector(1536),  -- OpenAI text-embedding-3-small

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_mindscape_personal_user ON mindscape_personal(user_id);
CREATE INDEX idx_mindscape_personal_source ON mindscape_personal(source_type);
CREATE INDEX idx_mindscape_personal_updated_at ON mindscape_personal(updated_at DESC);
CREATE INDEX idx_mindscape_personal_metadata ON mindscape_personal USING gin(metadata);

-- Vector index (created conditionally when data exists)
CREATE INDEX IF NOT EXISTS idx_mindscape_personal_embedding
ON mindscape_personal
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
```

**Additional Tables in PostgreSQL**:

- `playbook_knowledge`: Indexed playbook content for RAG
- `external_docs`: Synced external documents (WordPress, etc.)
- `mindscape_suggestions`: AI-generated suggestions

**Implementation Reference**: `backend/app/init_db.py:33-236`

---

### 5.4 Complete Database Architecture Overview

**SQLite Database** (`mindscape.db`):
- Core transactional data
- Tables: `profiles`, `intents`, `agent_executions`, `mind_events`, `intent_logs`, `workspaces`, `habit_observations`, `habit_candidates`, `habit_audit_logs`, `entities`, `tags`, `entity_tags`
- Fast local access
- Foreign key relationships

**PostgreSQL Database** (`mindscape_vectors`):
- Vector embeddings and semantic search
- Tables: `mindscape_personal`, `playbook_knowledge`, `external_docs`, `mindscape_suggestions`
- pgvector extension for similarity search
- Optimized for RAG queries

**Schema Initialization**: `backend/app/services/stores/schema.py:296-321`

---

### 5.5 Stores Architecture Pattern

**Domain-Specific Stores**: The system uses a domain-driven design pattern with specialized stores for each domain:

```python
# Base Store (common functionality)
class StoreBase:
    """Base class for all domain stores"""
    - Database connection management
    - Transaction support
    - JSON serialization/deserialization
    - Time format conversion

# Domain Stores
- ProfilesStore: Profile CRUD operations
- IntentsStore: Intent card management
- AgentExecutionsStore: Agent execution history
- EventsStore: Event timeline management
- IntentLogsStore: Intent governance audit logs
- WorkspacesStore: Workspace management
- EntitiesStore: Entity management
- HabitStore: Habit learning operations

# Unified Facade
class MindscapeStore:
    """Facade that provides unified interface to all stores"""
    - Delegates to domain-specific stores
    - Maintains backward compatibility
    - Handles schema initialization and migrations
```

**Benefits**:
- Clear separation of concerns
- Easy to test and maintain
- Consistent data access patterns
- Automatic schema initialization and migrations

**Implementation Reference**:
- Base store: `backend/app/services/stores/base.py:37-212`
- Unified facade: `backend/app/services/mindscape_store.py:36-459`
- All domain stores: `backend/app/services/stores/*.py`

---

## 6. Typical Data Flow

Standard flow starting from "user sends a command":

### 6.1 Complete Flow Diagram

```
User Input
    ↓
[Event Layer] Record user_message event
    ↓
[Intent Layer] Analyze intent
    ├─→ intent_type: "write_proposal"
    ├─→ topic: "government_grant"
    └─→ suggested_playbook: "major_proposal"
    ↓
[Playbook Runner] Start Playbook
    ↓
[Capability] Execute tools (e.g., assemble_full_proposal)
    ↓
[Event Layer] Record playbook_step event
    ├─→ is_complete: true
    ├─→ is_final_output: true
    └─→ metadata: { should_embed: true, is_artifact: true }
    ↓
[Memory Layer] Check should_generate_embedding()
    ├─→ Yes → Generate embedding → Write to mindscape_personal
    └─→ No → Only record event
    ↓
Return result to user
```

### 6.2 Code Example

```python
# 1. User input
user_message = "Help me write a government grant proposal"

# 2. Record event (Event Layer - always recorded)
event = MindEvent(
    id=str(uuid.uuid4()),
    timestamp=datetime.utcnow(),
    actor=EventActor.USER,
    channel="api",
    profile_id=profile_id,
    workspace_id=workspace_id,  # Workspace-aware
    event_type=EventType.MESSAGE,
    payload={"message": user_message, "role": "user"},
    metadata={}  # No embedding flag - will not generate embedding
)
events_store.create_event(event, generate_embedding=False)  # Default: opt-in

# 3. Intent analysis (Intent Governance Layer)
intent_result = await intent_pipeline.analyze(user_message, context)
# Intent analysis result logged to intent_logs table automatically

# 4. Start Playbook
execution_result = await playbook_runner.start_playbook(
    playbook_code=intent_result.selected_playbook_code,
    inputs={"topic": intent_result.task_domain},
    workspace_id=workspace_id
)

# 5. Record final output when playbook completes (Event Layer + Memory Layer)
if execution_result.is_complete:
    final_event = MindEvent(
        id=str(uuid.uuid4()),
        timestamp=datetime.utcnow(),
        actor=EventActor.ASSISTANT,
        channel="playbook",
        profile_id=profile_id,
        workspace_id=workspace_id,
        event_type=EventType.PLAYBOOK_STEP,
        payload={
            "execution_id": execution_result.execution_id,
            "is_complete": True,
            "is_final_output": True,
            "structured_output": execution_result.structured_output
        },
        metadata={
            "should_embed": True,  # Explicit flag to generate embedding
            "is_final": True,
            "is_artifact": True
        }
    )
    # This will:
    # 1. Record event in mind_events (SQLite)
    # 2. Check should_generate_embedding() -> returns True
    # 3. Generate embedding asynchronously
    # 4. Store in mindscape_personal (PostgreSQL)
    events_store.create_event(final_event, generate_embedding=True)
```

---

## 7. Implementation Details

### 7.1 EventsStore

```python
class EventsStore:
    def create_event(
        self,
        event: MindEvent,
        generate_embedding: bool = False
    ) -> MindEvent:
        """
        Create a new mindspace event

        Args:
            event: MindEvent to create
            generate_embedding: Whether to automatically generate embedding for this event

        Returns:
            Created MindEvent
        """
        # 1. Write to mind_events table (SQLite)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO mind_events (
                    id, timestamp, actor, channel, profile_id, project_id, workspace_id,
                    event_type, payload, entity_ids, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                event.id,
                self.to_isoformat(event.timestamp),
                event.actor.value,
                event.channel,
                event.profile_id,
                event.project_id,
                event.workspace_id,
                event.event_type.value,
                self.serialize_json(event.payload),
                self.serialize_json(event.entity_ids),
                self.serialize_json(event.metadata)
            ))
            conn.commit()

        # 2. Conditionally generate embedding (asynchronously, non-blocking)
        if generate_embedding:
            try:
                from ..event_embedding_generator import EventEmbeddingGenerator
                import asyncio

                generator = EventEmbeddingGenerator()
                # Run async in background (fire and forget)
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(generator.generate_embedding_for_event(event))
                    else:
                        asyncio.run(generator.generate_embedding_for_event(event))
                except RuntimeError:
                    asyncio.run(generator.generate_embedding_for_event(event))
            except Exception as e:
                # Don't fail event creation if embedding generation fails
                logger.warning(f"Failed to generate embedding for event {event.id}: {e}")

        return event
```

**Implementation Reference**: `backend/app/services/stores/events_store.py:18-74`

### 7.2 EventEmbeddingGenerator

```python
class EventEmbeddingGenerator:
    async def generate_embedding_for_event(self, event: MindEvent) -> Optional[str]:
        """
        Generate embedding for an event if it meets criteria

        Args:
            event: MindEvent to process

        Returns:
            Embedding ID if generated, None otherwise
        """
        # 1. Check if should generate (selective strategy)
        if not self.should_generate_embedding(event):
            logger.debug(f"Skipping embedding for event {event.id}: doesn't meet criteria")
            return None

        # 2. Check if already exists
        if self._check_existing_embedding(event):
            logger.debug(f"Embedding already exists for event {event.id}")
            return None

        # 3. Extract text content from event payload
        text = self._extract_text_from_event(event)
        if not text:
            logger.warning(f"No text content found in event {event.id}")
            return None

        # 4. Generate embedding using configured embedding model
        embedding = await self._generate_embedding(text)

        # 5. Write to mindscape_personal (PostgreSQL)
        embedding_id = self._store_embedding(event, text, embedding)

        return embedding_id
```

**Implementation Reference**: `backend/app/services/event_embedding_generator.py:93-333`

### 7.3 Key File Locations

**Models**:
- **Event Models**: `backend/app/models/mindscape.py:275-323` (EventType, EventActor, MindEvent)
- **Habit Models**: `backend/app/models/habit.py` (HabitObservation, HabitCandidate, HabitAuditLog)
- **Intent Log Model**: `backend/app/models/mindscape.py` (IntentLog)

**Stores (Domain-Specific Data Access)**:
- **Base Store**: `backend/app/services/stores/base.py` (StoreBase class)
- **Events Store**: `backend/app/services/stores/events_store.py` (EventsStore)
- **Intent Logs Store**: `backend/app/services/stores/intent_logs_store.py` (IntentLogsStore)
- **Profiles Store**: `backend/app/services/stores/profiles_store.py` (ProfilesStore)
- **Intents Store**: `backend/app/services/stores/intents_store.py` (IntentsStore)
- **Workspaces Store**: `backend/app/services/stores/workspaces_store.py` (WorkspacesStore)
- **Entities Store**: `backend/app/services/stores/entities_store.py` (EntitiesStore)
- **Agent Executions Store**: `backend/app/services/stores/agent_executions_store.py` (AgentExecutionsStore)
- **Habit Store**: `backend/app/services/habit_store.py` (HabitStore)
- **Unified Store**: `backend/app/services/mindscape_store.py` (MindscapeStore - unified interface)

**Database Schema**:
- **Schema Definitions**: `backend/app/services/stores/schema.py` (all table definitions)
- **Migrations**: `backend/app/services/stores/migrations/migration_001_add_workspace_id.py` (workspace_id migration)

**Services**:
- **Embedding Generation**: `backend/app/services/event_embedding_generator.py` (EventEmbeddingGenerator)
- **Intent Analysis**: `backend/app/services/intent_analyzer.py` (IntentPipeline, 3-layer analysis)
- **Playbook Execution**: `backend/app/services/playbook_runner.py` (PlaybookRunner)

**PostgreSQL Tables**:
- **Initialization**: `backend/app/init_db.py:33-236` (mindscape_personal, playbook_knowledge, external_docs, mindscape_suggestions)

---

## 8. Current Implementation Status

### ✅ Completed

**Event Layer**:
- Event models and storage mechanism (`mind_events` table in SQLite)
- Comprehensive event type coverage (11 event types: MESSAGE, TOOL_CALL, PLAYBOOK_STEP, INSIGHT, HABIT_OBSERVATION, PROJECT_CREATED, PROJECT_UPDATED, INTENT_CREATED, INTENT_UPDATED, AGENT_EXECUTION, OBSIDIAN_NOTE_UPDATED)
- Workspace support in events (workspace_id field, migration 001)
- Event filtering by profile, project, workspace, event_type, time range
- Domain-specific stores architecture (EventsStore, IntentLogsStore, etc.)

**Intent Governance Layer**:
- 3-layer intent analysis pipeline (Interaction Type → Task Domain → Playbook Selection)
- Intent logs table (`intent_logs`) for audit trail
- Workspace-aware intent tracking (workspace_id field)
- Rule-based and LLM-based intent matching
- User override support in intent logs

**Memory/Embedding Layer**:
- Selective embedding generation logic (opt-in, not opt-out)
- Automatic marking of final outputs when playbooks complete
- Automatic marking when intents complete/high priority
- Artifact recording when Major Proposal capability completes
- PostgreSQL + pgvector integration for embeddings
- `mindscape_personal` table in PostgreSQL with vector search
- `playbook_knowledge` table for playbook content indexing
- `external_docs` table for external document synchronization
- `mindscape_suggestions` table for AI-generated suggestions

**Additional Systems**:
- Workspaces system (workspaces table, workspace-aware events and intents)
- Habit Learning system (habit_observations, habit_candidates, habit_audit_logs tables)
- Entity and Tag system (entities, tags, entity_tags tables)
- Database migration system (migration_001_add_workspace_id)

### ⚠️ Pending

- Artifact recording when Storyboard capability completes (pending API routes)
- Text extraction and conditional embedding for file uploads
- UI operation for user-explicit "Save to Knowledge Base" marking

### 📊 Architecture Notes

**Database Architecture**:
- **SQLite** (`mindscape.db`): Core transactional data
  - `profiles`, `intents`, `agent_executions`: Core user data
  - `mind_events`: Event timeline (all events)
  - `intent_logs`: Intent governance audit trail
  - `workspaces`: Workspace management
  - `habit_observations`, `habit_candidates`, `habit_audit_logs`: Habit learning system
  - `entities`, `tags`, `entity_tags`: Entity and tag system
- **PostgreSQL + pgvector**: Vector embeddings and semantic search
  - `mindscape_personal`: Personal knowledge embeddings
  - `playbook_knowledge`: Playbook content embeddings
  - `external_docs`: External document embeddings
  - `mindscape_suggestions`: AI-generated suggestions

**Event Storage**:
- Events stored in SQLite `mind_events` table (not PostgreSQL)
- Embeddings generated asynchronously and stored in PostgreSQL
- Workspace-aware event tracking (workspace_id field)
- Selective embedding strategy: only stable artifacts get embedded

**Intent Governance**:
- 3-layer analysis pipeline (Interaction Type → Task Domain → Playbook Selection)
- All analysis results logged to `intent_logs` table
- Workspace-aware intent tracking (workspace_id field)

**Habit Learning**:
- Observes user behavior patterns
- Generates habit candidates with confidence scores
- Full audit trail for habit changes
- Applied to profile preferences automatically when confirmed

**Stores Architecture**:
- Domain-specific stores pattern (ProfilesStore, IntentsStore, EventsStore, etc.)
- Unified MindscapeStore facade for backward compatibility
- Automatic schema initialization and migration system
- Base Store class provides common functionality (transactions, JSON serialization)

**Database Migrations**:
- Migration system supports incremental schema changes
- Migration 001: Added workspace_id to mind_events and intent_logs tables
- Migrations run automatically on store initialization

---

## References

For additional implementation details and developer guidelines, see the architecture documentation index.

## Related Code Files

**Core Models**:
- `backend/app/models/mindscape.py` - Event, Intent, Profile models
- `backend/app/models/habit.py` - Habit learning models
- `backend/app/models/workspace.py` - Workspace model

**Core Services**:
- `backend/app/services/stores/schema.py` - All table definitions
- `backend/app/services/stores/events_store.py` - Event storage
- `backend/app/services/stores/intent_logs_store.py` - Intent logs storage
- `backend/app/services/event_embedding_generator.py` - Embedding generation
- `backend/app/services/intent_analyzer.py` - Intent analysis pipeline
- `backend/app/services/mindscape_store.py` - Unified store facade
- `backend/app/services/habit_store.py` - Habit learning operations

**Database Initialization**:
- `backend/app/init_db.py` - PostgreSQL tables (vector embeddings)
- `backend/app/services/stores/schema.py` - SQLite tables (core data)
- `backend/app/services/stores/migrations/` - Database migrations
