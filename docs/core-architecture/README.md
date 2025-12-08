# Architecture Documentation

This directory contains the complete architecture documentation for Mindscape AI, including system architecture, core concepts, and implementation status.

## Start Here

**New to the architecture?** Read [System Overview](./system-overview.md) first to understand how all layers work together to deliver the **AI-driven visible thinking workflow** described in the main README.

## Current Implementation Status

**Project + Flow + Sandbox Architecture (v2.0)** - Fully implemented and in production.

- **Project Management**: Complete lifecycle management (create, update, close, archive)
- **Project Detection**: Automatic project suggestion from conversations
- **Playbook Flow Execution**: Multi-playbook orchestration with dependency resolution
- **Project Sandbox**: Workspace-isolated file space for each project
- **Artifact Registry**: Automatic artifact tracking and registration
- **Layered Memory System**: Workspace core, project, and member profile memories
- **Flow Checkpointing**: Resume execution from any node
- **API Endpoints**: Full REST API for projects and flows

**Core System Architecture**:

- **Port/Adapter Pattern**: Clean separation between core and adapters
- **Execution Context**: Context abstraction flowing through the system
- **Memory & Intent Architecture**: Three-layer architecture (Signal, Intent Governance, Execution)
- **Playbook System**: Multi-step workflow execution

### 📋 Implementation Details

#### Project Model
- **Location**: `backend/app/models/project.py`
- **Key Fields**: `id`, `type`, `title`, `home_workspace_id`, `flow_id`, `state`
- **Ownership**: `initiator_user_id`, `human_owner_user_id`, `ai_pm_id`
- **Database**: `projects` table with indexes on workspace, state, created_at

#### Flow Execution
- **Location**: `backend/app/services/project/flow_executor.py`
- **Features**: Topological sorting, dependency resolution, partial retry, checkpointing
- **Integration**: Works with `PlaybookRunner` and `ProjectSandboxManager`

#### Sandbox Management
- **Location**: `backend/app/services/project/project_sandbox_manager.py`
- **Path Structure**: `sandboxes/{workspace_id}/{project_type}/{project_id}/`
- **Isolation**: Complete workspace-level isolation

#### Memory Layering
- **Workspace Core Memory**: `backend/app/services/memory/workspace_core_memory.py`
- **Project Memory**: `backend/app/services/memory/project_memory.py`
- **Member Profile Memory**: `backend/app/services/memory/member_profile_memory.py`
- **Integration**: Automatically loaded by `ContextBuilder` for LLM context

## Directory Structure

### System Overview

#### [System Overview: AI-Driven Visible Thinking Workflow](./system-overview.md)
Complete flow from user to artifact, showing how all architectural layers work together. Maps the README's "AI-driven visible thinking workflow" concept to actual system components.

### Core System Architecture

#### [Port Architecture](./port-architecture.md)
System architecture and design patterns using Port/Adapter pattern (Hexagonal Architecture).

#### [Execution Context](./execution-context.md)
Execution context abstraction and how it flows through the system.

#### [Memory & Intent Architecture](./memory-intent-architecture.md)
Event, intent, and memory layer design - the three-layer Mindscape architecture.

#### [Local/Cloud Boundary](./local-cloud-boundary.md)
Architectural separation principles between local and cloud implementations.

#### [Playbooks & Multi-step Workflows](./playbooks-and-workflows.md)
Playbook architecture and workflow execution mechanisms.

#### [Long-chain Execution](./long-chain-execution/local/long-chain-execution-local-core.md)
Long-chain execution patterns for complex workflows.

#### [Sandbox System](./sandbox/)
System-level Sandbox architecture, unifying all AI write operations.

- [Sandbox System Summary](./sandbox/sandbox-system-summary.md)

#### [Project + Flow](./project-flow/)
Project and Playbook Flow architecture for multi-playbook collaboration.

- [Project + Flow Summary](./project-flow/project-flow-summary.md)


## Core Concepts

### Mindscape Architecture (3 Layers)

1. **Signal Layer** - Collects all signals (conversations, files, tool responses, playbook results)
2. **Intent Governance Layer** - Organizes signals into IntentCards and IntentClusters
3. **Execution & Semantic Layer** - Executes playbooks, tools, and semantic engines

### Project + Flow + Sandbox Architecture (v2.0)

**Project**: Deliverable-level container with its own lifecycle (open, closed, archived)
- **Auto-detection**: Projects emerge naturally from conversations
- **PM Assignment**: Automatic suggestion of human and AI PMs
- **State Management**: open → closed → archived lifecycle

**Sandbox**: Unified file space shared across all playbooks in a project
- **Path**: `sandboxes/{workspace_id}/{project_type}/{project_id}/`
- **Isolation**: Complete workspace-level isolation
- **Integration**: Automatically passed to playbook executions

**Playbook Flow**: Multi-playbook orchestration with dependency resolution
- **Topological Sorting**: Automatic execution order resolution
- **Checkpointing**: Resume from any node
- **Artifact Preservation**: Automatic artifact registration
- **Error Handling**: Retry with exponential backoff

**Value**:
- Unified worldview (same files/specs)
- Execution order enforcement
- Deliverable-level container
- Automatic project detection from conversations

### Port/Adapter Pattern

Mindscape AI uses Port interfaces to maintain clean boundaries:
- **IdentityPort**: Execution context management
- **IntentRegistryPort**: Intent resolution
- **PlaybookExecutorPort**: Playbook execution

## API Endpoints

### Projects API

- `GET /api/v1/workspaces/{workspace_id}/projects` - List projects
- `GET /api/v1/workspaces/{workspace_id}/projects/{project_id}` - Get project
- `POST /api/v1/workspaces/{workspace_id}/projects` - Create project
- `POST /api/v1/workspaces/{workspace_id}/projects/{project_id}/execute-flow` - Execute flow
- `GET /api/v1/workspaces/{workspace_id}/projects/{project_id}/flow-status` - Get flow status

### Flows API

- `POST /api/v1/workspaces/{workspace_id}/flows` - Create flow
- `GET /api/v1/workspaces/{workspace_id}/flows` - List flows
- `GET /api/v1/workspaces/{workspace_id}/flows/{flow_id}` - Get flow
- `PUT /api/v1/workspaces/{workspace_id}/flows/{flow_id}` - Update flow
- `DELETE /api/v1/workspaces/{workspace_id}/flows/{flow_id}` - Delete flow
- `GET /api/v1/workspaces/{workspace_id}/flows/name/{flow_name}` - Get flow by name

## Database Schema

### Projects Table

```sql
CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    home_workspace_id TEXT NOT NULL,
    flow_id TEXT NOT NULL,
    state TEXT DEFAULT 'open',
    initiator_user_id TEXT NOT NULL,
    human_owner_user_id TEXT,
    ai_pm_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT
);
```

### Artifact Registry Table

```sql
CREATE TABLE artifact_registry (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT
);
```

### Playbook Flows Table

```sql
CREATE TABLE playbook_flows (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    flow_definition TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Reading Guide

### Quick Overview
1. [System Overview](./system-overview.md) - **Start here**: Complete flow from user to artifact
2. [Port Architecture](./port-architecture.md) - System design patterns
3. [Memory & Intent Architecture](./memory-intent-architecture.md) - Three-layer architecture
4. [Sandbox System Summary](./sandbox/sandbox-system-summary.md)
5. [Project + Flow Summary](./project-flow/project-flow-summary.md)

### Deep Dive
1. [Port Architecture](./port-architecture.md) - Hexagonal architecture patterns
2. [Execution Context](./execution-context.md) - Context flow
3. [Local/Cloud Boundary](./local-cloud-boundary.md) - Separation principles
4. [Playbooks & Multi-step Workflows](./playbooks-and-workflows.md) - Workflow execution
5. [Sandbox System Summary](./sandbox/sandbox-system-summary.md)
6. [Project + Flow Summary](./project-flow/project-flow-summary.md)

### Getting Started
1. [System Overview](./system-overview.md) - Complete workflow overview
2. [Sandbox System Summary](./sandbox/sandbox-system-summary.md)
3. [Project + Flow Summary](./project-flow/project-flow-summary.md)

## Architecture Relationship

```
Workspace (long-term room, years of collaboration)
    ↓
Conversation → Project Detector → Project Suggestion
    ↓
Project (deliverable container, has its own lifecycle)
    ↓
Playbook Flow (execution flow with dependency resolution)
    ↓
Shared Sandbox (file world: sandboxes/{workspace_id}/{project_type}/{project_id}/)
    ↓
SandboxManager (system-level)
```

## Key Implementation Files

### Models
- `backend/app/models/project.py` - Project model
- `backend/app/models/playbook_flow.py` - Flow, FlowNode, FlowEdge models
- `backend/app/models/artifact_registry.py` - ArtifactRegistry model

### Services
- `backend/app/services/project/project_manager.py` - Project lifecycle management
- `backend/app/services/project/project_detector.py` - Automatic project detection
- `backend/app/services/project/project_assignment_agent.py` - PM assignment
- `backend/app/services/project/flow_executor.py` - Flow execution engine
- `backend/app/services/project/project_sandbox_manager.py` - Sandbox management
- `backend/app/services/project/artifact_registry_service.py` - Artifact tracking
- `backend/app/services/memory/workspace_core_memory.py` - Workspace memory
- `backend/app/services/memory/project_memory.py` - Project memory
- `backend/app/services/memory/member_profile_memory.py` - Member memory

### Stores
- `backend/app/services/stores/projects_store.py` - Project persistence
- `backend/app/services/stores/playbook_flows_store.py` - Flow persistence

### API Routes
- `backend/features/workspace/projects/routes.py` - Projects API
- `backend/features/workspace/flows/routes.py` - Flows API

### Integration
- `backend/app/services/conversation_orchestrator.py` - Project detection integration
- `backend/app/services/playbook_runner.py` - Project mode support
- `backend/app/services/conversation/context_builder.py` - Memory layering integration

## Mapping: README Concepts to Architecture

The main README describes two key concepts:

1. **AI-driven visible thinking workflow** = Signal → Intent Governance → Project/Flow → Playbooks → Sandbox → Memory
   - See [System Overview](./system-overview.md) for the complete flow

2. **Project / Playbook flow** = Project → Intents → Playbooks → AI Team Execution → Artifacts
   - See [Project + Flow Architecture](./project-flow/project-flow-architecture.md) for technical details
   - See [System Overview](./system-overview.md) for examples and mental model

## For Contributors: How to Extend

### Adding a New Playbook

1. Create `playbook.md` (human-readable workflow) and `playbook.json` (machine-executable config)
2. Define steps, AI roles, tools, and expected outputs
3. Register in playbook registry
4. See [Playbooks & Multi-step Workflows](./playbooks-and-workflows.md) for detailed guide

### Adding a New Port / Adapter

1. Define Port interface in `backend/app/ports/`
2. Implement Local adapter in `backend/app/services/adapters/`
3. Inject Port into core services via dependency injection
4. See [Port Architecture](./port-architecture.md) for patterns and examples

### Adding a New Memory Model / Event Type

1. Define new EventType enum in `backend/app/models/workspace.py`
2. Add schema to `events` table if needed (via Alembic migration)
3. Update `should_generate_embedding()` logic if embedding is needed
4. Implement memory service if workspace/project/member-specific
5. Integrate into ContextBuilder for LLM context
6. See [Memory & Intent Architecture](./memory-intent-architecture.md) for schema and patterns

### Adding a New Tool / Integration

1. Implement tool provider in `backend/app/services/tools/providers/`
2. Register in tool registry
3. Add to playbook tool list if needed
4. See tool registry documentation for details

---
