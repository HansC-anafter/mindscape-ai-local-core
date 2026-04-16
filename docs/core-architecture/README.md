# Architecture Documentation

This directory contains the architecture documentation for Mindscape AI Local Core, including the current public framing, planning/runtime boundaries, and the deeper implementation-oriented references that support them.

## Start Here

**New to the architecture?** Read these in order:

1. [System Overview](./system-overview.md) — the public architecture after `SpatialSchedulingIR` becomes a first-class planning artifact
2. [Spatial Runtime Planning](./spatial-runtime-planning.md) — how `TaskIR` and `SpatialSchedulingIR` divide responsibilities
3. [Governed Memory Fabric](./governed-memory-fabric.md) — what the memory layer stores, and what it must not store
4. [Mind Meeting — Five-Layer Architecture](./meeting-engine-dispatch.md) — the meeting pipeline that emits the bounded artifacts
5. [Local/Cloud Boundary](./local-cloud-boundary.md) — where local-core stops and installable/runtime packs begin

## Current Architecture Status

The current public framing is:

> **Governance Context → Meeting Runtime ↔ Governed Memory Fabric → TaskIR / SpatialSchedulingIR → Consumer Runtimes / Optional Local Actuation → Artifacts, Runtime Receipts, and World Summary / Writeback**

Key points:

- **Governance Context** defines why work matters, how trade-offs are made, and what boundaries cannot be crossed.
- **Meeting Runtime** performs live deliberation, clarification, convergence, dispatch, and closure.
- **TaskIR** is the control-plane artifact for execution-ready work.
- **SpatialSchedulingIR** is the planning-plane artifact for spatial/world execution intent when a workflow needs it.
- **Governed Memory Fabric** serves continuity into the meeting and ingests bounded summaries back after execution.
- **Consumer Runtimes / Optional Local Actuation** include the project/playbook/tool stack plus installed runtime packs and external execution environments.

Important public-safe boundaries:

- local-core owns governance, bounded planning, and bounded writeback
- installable/runtime packs own provider-specific execution logic
- pack workbench/product UI source is pack-owned via `manifest.yaml`
  `ui_components`, while Local-Core hosts the installed runtime shell/loader
- world memory stores summaries, refs, and traceability keys rather than raw provider payloads
- `Project / Flow / Playbook / Sandbox` remain an important consumer path, but they are not the only public mental model anymore

### Architecture Components

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

#### Memory Surfaces
- **Workspace Core Memory**: `backend/app/services/memory/workspace_core_memory.py`
- **Project Memory**: `backend/app/services/memory/project_memory.py`
- **Member Profile Memory**: `backend/app/services/memory/member_profile_memory.py`
- **Architecture Direction**: These surfaces are converging toward a governed memory fabric with explicit episodic/core/procedural layers and serving projections

## Directory Structure

### System Overview

#### [System Overview: Mindscape Engine](./system-overview.md)
Complete flow from governance context to runtime, memory, and optional actuation. Maps the README's public engine framing to actual system components.

### Core System Architecture

#### [Port Architecture](./port-architecture.md)
System architecture and design patterns using Port/Adapter pattern (Hexagonal Architecture).

#### [Execution Context](./execution-context.md)
Execution context abstraction and how it flows through the system.

#### [Execution Context Four-Layer Model](./execution-context-four-layer-model.md)
Conceptual framework for understanding execution context layers: Task/Policy/Lens/Assets. Maps existing fields to four-layer model without structural changes.

#### [Mind Lens](./mind-lens.md)
Mind Lens core architecture - perspective/viewpoint system for how to see, where to focus attention, and how to make trade-offs.

#### [Lens Composition](./lens-composition.md)
Lens Composition architecture - multi-lens combination recipes with fusion strategies for complex scenarios.

#### [Surface & Command Bus](./surface-command-bus.md)
Surface and Command Bus architecture for unified command dispatch and event collection across all channels, with BYOP/BYOL trace support.

#### [Governed Memory Fabric](./governed-memory-fabric.md)
Current public architecture story for memory in Mindscape: meeting runtime, governed memory, long-term continuity, and serving boundaries.

#### [Legacy Event, Intent, and Memory/Embedding Architecture](./memory-intent-architecture.md)
Historical implementation-oriented reference for the earlier event -> intent -> memory/embedding framing.

#### [Local/Cloud Boundary](./local-cloud-boundary.md)
Architectural separation principles between local and cloud implementations.

#### [Playbooks & Multi-step Workflows](./playbooks-and-workflows.md)
Playbook architecture and workflow execution mechanisms, including identity governance and access control.

#### [Execution Chat Agent Loop](./execution-chat-agent-loop.md)
Architecture and implementation details for upgrading execution-scoped chat from prompt-only discussion to an LLM + tool executor loop, while preserving legacy discussion mode and Local-Core governance boundaries.

#### [Workspace Generic Execution Operator Toolbar Revision](./workspace-generic-execution-operator-toolbar-revision.md)
Corrective implementation plan for restoring the proper boundary: cloud repo remains pack authoring/packaging only, while Local-Core remains the runtime host for workspace-generic execution operator surfaces and execution-chat runtime.

#### [Workbench Execution Chat Entry](./workbench-execution-chat-entry.md)
Historical draft of the earlier pack-launched entry model. Kept for audit only.
Do not use it to infer pack workbench ownership; use the toolbar revision
document above plus pack `manifest.yaml` `ui_components` as the current source
of truth.

#### [Workspace Execution Operator Toolbar Cleanup Checklist](./workspace-execution-operator-toolbar-cleanup-checklist-2026-03-22.md)
Executed cleanup checklist for removing the rejected Local-Core launcher/context-menu experiment while preserving the canonical Local-Core execution runtime.

#### [Governance Decision & Risk Control Layer](./governance-decision-risk-control-layer.md)
Multi-layered governance framework for safe and controlled playbook execution, with clear separation between Local-Core universal mechanisms and Cloud-specific extensions.

#### [Mind-Model VC](./mind-model-vc.md)
Version control for mind models - organizes user-provided clues into reviewable, adjustable, and rollback-able mind state recipes with version history.

#### [Asset Provenance](./asset-provenance.md)
Segment-level provenance architecture for AI-generated content - Asset/Revision/Segment/Take/Selection model enabling fine-grained rollback and traceability.

#### [Prompt Compilation](./prompt-compilation.md)
Three-layer prompt compilation architecture (Raw → Compiled → Semantic) showing how user intent, Mind-Lens styling, and memory injection combine before reaching the LLM.

#### [Tool RAG Search](./tool-rag-search.md)
Semantic tool discovery architecture — how the meeting engine and context builder retrieve relevant tools for a user query using pgvector embeddings. Covers multi-model Reciprocal Rank Fusion (RRF), TTL caching, cold-start auto-indexing, and the embedding model priority chain.

#### [Long-chain Execution](./long-chain-execution/local/long-chain-execution-local-core.md)
Long-chain execution patterns for complex workflows.

#### [MCP Gateway](./mcp-gateway.md)
Model Context Protocol Gateway architecture for exposing Mindscape capabilities to external AI tools (Claude Desktop, Cursor IDE, custom integrations). Includes three-layer tool governance, auto-provision, and context passthrough.

#### [Cloud Connector](./cloud-connector.md)
Platform-agnostic WebSocket bridge for connecting Local-Core to any compatible cloud platform. Handles execution requests, event reporting, messaging, and heartbeat monitoring.

#### [Mind Meeting — Five-Layer Architecture](./meeting-engine-dispatch.md)
Unified five-layer meeting architecture: deliberation, semantic bridge, convergence engine, dispatch, and supervision. Inherits from the Mindscape Node Graph (Mind Canvas).

#### [Runtime Environments](./runtime-environments.md)
Multi-runtime management architecture for executing playbooks and tools across local and remote backends. Includes settings extension panels and auto-discovery.

#### [Local Runtime Persistence Topology](./local-runtime-persistence-topology.md)
Canonical local-core runtime data-root policy for `workspaces`, `storage`, `models`, `runtimes`, and their Docker mount mappings. Read this when changing host persistence paths, compose env policy, or any pack that assumes `/root/.mindscape/*`.

#### [Sandbox System](./sandbox/)
System-level Sandbox architecture, unifying all AI write operations.

- [Sandbox System Summary](./sandbox/sandbox-system-summary.md)

#### [Project + Flow](./project-flow/)
Project and Playbook Flow architecture for multi-playbook collaboration.

- [Project + Flow Summary](./project-flow/project-flow-summary.md)


## Core Concepts

### Mindscape Operating Engine

1. **Governance Context** - Intent + Lens + Policy define what matters, how to see, and what cannot be violated
2. **Meeting Runtime** - Handles live deliberation, clarification, convergence, dispatch, and loop closure
3. **TaskIR Control Plane** - Packages execution-ready work, dependencies, and dispatch boundaries
4. **SpatialSchedulingIR Planning Plane** - Packages bounded spatial/world execution intent when the workflow needs scene, subject, object, or camera-aware planning
5. **Governed Memory Fabric** - Preserves evidence, builds episodes, promotes durable memory, and serves continuity back into execution
6. **Consumer Runtimes / Optional Local Actuation** - Project / Flow + Playbooks / Tools + Sandbox / installed runtime packs + external runtimes

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
3. [Governed Memory Fabric](./governed-memory-fabric.md) - Current public memory architecture
4. [Legacy Event, Intent, and Memory/Embedding Architecture](./memory-intent-architecture.md) - Historical reference
5. [Sandbox System Summary](./sandbox/sandbox-system-summary.md)
6. [Project + Flow Summary](./project-flow/project-flow-summary.md)

### Deep Dive
1. [Port Architecture](./port-architecture.md) - Hexagonal architecture patterns
2. [Execution Context](./execution-context.md) - Context flow
3. [Local/Cloud Boundary](./local-cloud-boundary.md) - Separation principles
4. [Playbooks & Multi-step Workflows](./playbooks-and-workflows.md) - Workflow execution, identity governance, and access control
5. [Governance Decision & Risk Control Layer](./governance-decision-risk-control-layer.md) - Multi-layered governance framework
6. [Sandbox System Summary](./sandbox/sandbox-system-summary.md)
7. [Project + Flow Summary](./project-flow/project-flow-summary.md)

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

## Key Code Files

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

1. **Mindscape Engine** = Governance Context → Meeting Runtime ↔ Governed Memory Fabric → Optional Actuation
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
6. See [Governed Memory Fabric](./governed-memory-fabric.md) for architecture direction and [Legacy Event, Intent, and Memory/Embedding Architecture](./memory-intent-architecture.md) for older schema patterns

### Adding a New Tool / Integration

1. **For External Contributors**: See [Adapter Compilation Guide](../contributor-guide/adapter-compilation-guide.md) - Complete ABI guide for wrapping tools, creating playbooks, and publishing packs
2. **For Internal Development**: Implement tool provider in `backend/app/services/tools/providers/`
3. Register in tool registry
4. Add to playbook tool list if needed
5. See tool registry documentation for details

---
