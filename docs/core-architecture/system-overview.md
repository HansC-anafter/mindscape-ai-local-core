# System Overview: AI-Driven Visible Thinking Workflow

This document provides a complete system overview, showing how all architectural layers work together to deliver the **AI-driven visible thinking workflow** described in the main README.

## The Complete Flow: From User to Artifact

```text
User / Workspace UI / LINE / IG / WP (Surfaces)
    ↓
Surface & Command Bus (unified command dispatch)
    ↓
Conversation Orchestrator (+ IdentityPort → ExecutionContext)
    ↓
Event Layer (MindEvent + SurfaceEvent)
    ↓
Intent Governance Layer
    ↓
Mind-Model VC Layer (Swatch → Mix → Commit)
    ↓
Project Detector + Project / Flow
    ↓
Playbook Runner (playbook.md + playbook.json)
    ↓
Sandbox (project file world)
    ↓
Event + Memory Layer (SQLite + pgvector)
    ↓
Artifacts & Decisions
```

## AI-Driven Visible Thinking Workflow

The **AI-driven visible thinking workflow** can be expressed as:

> **Signal → Intent Governance → Mind-Model VC → Project/Flow → Playbooks → Sandbox → Memory**

### Layer-by-Layer Breakdown

#### 1. User / Workspace UI
- User interacts with the workspace through the web console
- Conversations, file uploads, and manual triggers enter the system
- Timeline view shows execution traces and artifacts

#### 1.5. Surface & Command Bus
- **Surface**: Input/output channels (UI, LINE, IG, WordPress, etc.)
- **Command Bus**: Unified command dispatch across all surfaces
- **Event Stream**: Cross-channel event collection with BYOP/BYOL trace support
- **Surface Types**: CONTROL (UI) vs DELIVERY (LINE, IG, WP)
- **BYOP/BYOL Integration**: Automatic extraction and persistence of collaboration fields (pack_id, card_id, scope, playbook_version)
- See [Surface & Command Bus Architecture](./surface-command-bus.md) for details

#### 2. Conversation Orchestrator
- **Entry Point**: `ConversationOrchestrator.route_message()`
- **IdentityPort**: Resolves user context (workspace, profile)
- **ExecutionContext**: Flows through all layers with actor/workspace context
- **Project Detection**: Automatically detects if conversation warrants a new Project
- **Intent Extraction**: Extracts intents from user messages
- **Capability profiles & staged model routing**: selects different LLM capability profiles (FAST, STANDARD, PRECISE, TOOL_STRICT, SAFE_WRITE, etc.) for different phases
  (intent analysis, tool-candidate selection, planning, safe writes), while keeping all intermediate results as typed JSON IR instead of ad-hoc text.

#### 3. Event Layer (MindEvent)
- All user actions and system events become `MindEvent` objects
- Events are stored in SQLite (`events` table)
- Events feed into Intent Governance Layer
- Timeline visualization shows event history

#### 4. Intent Governance Layer
- **Intent Extraction**: Converts events into structured IntentCards
- **Intent Clustering**: Groups related intents into IntentClusters (Projects)
- **Intent Steward**: Maintains intent lifecycle and relationships
- **Memory Integration**: Connects to workspace/project/member memories

#### 4.5. Mind-Model VC Layer
- **Swatch Collection**: Extracts candidate clues from Events (requires user confirmation)
- **Mix Drafting**: Generates recipe drafts for time windows (user writes title/description)
- **Commit Tracking**: Records recipe changes with user-written commit messages
- **Co-Graph**: Tracks co-occurrence relationships between clues/colors
- **User Control**: All clues require confirmation; recipes require user-written descriptions
- See [Mind-Model VC Architecture](./mind-model-vc.md) for details

#### 5. Project Detector + Project / Flow
- **Project Detector**: LLM-based detection of project-worthy conversations
- **Project Creation**: Automatic or user-confirmed project creation
- **Project Assignment**: Suggests human and AI PMs
- **Flow Association**: Each Project has a PlaybookFlow
- **Project Memory**: Project-specific decision history and context

#### 6. Mind Lens & Lens Composition
- **Mind Lens**: Perspective/viewpoint system - how to see, where to focus attention, how to make trade-offs
- **Lens Composition**: Multi-lens combination recipes for complex scenarios
- **Fusion Strategies**: Priority, weighted, or priority-then-weighted fusion
- **Execution Context Integration**: Lens values influence how tasks are interpreted
- See [Mind Lens Architecture](./mind-lens.md) and [Lens Composition Architecture](./lens-composition.md) for details

#### 7. Playbook Runner
- **Playbook Execution**: Executes `playbook.md + playbook.json`
- **AI Team Roles**: Multiple AI roles collaborate (planner, writer, analyst)
- **Tool Calls**: Playbooks can call tools (filesystem, API, etc.)
- **Execution Trace**: Every step is logged and visible
- **Project Mode**: Playbooks can access project sandbox and context
- **Lens Integration**: Playbook execution uses resolved lens values from Execution Context

#### 8. Sandbox (Project File World)
- **Path Structure**: `sandboxes/{workspace_id}/{project_type}/{project_id}/`
- **Shared Space**: All playbooks in a project share the same sandbox
- **Artifact Storage**: Generated files, drafts, and intermediate results
- **Workspace Isolation**: Complete isolation between workspaces

#### 9. Event + Memory Layer
- **SQLite**: Core data (workspaces, projects, events, intents)
- **pgvector**: Vector embeddings for semantic search
- **Memory Services**:
  - Workspace Core Memory (brand, voice, constraints)
  - Project Memory (decisions, version evolution)
  - Member Profile Memory (skills, preferences)
- **Context Builder**: Assembles memory context for LLM prompts

#### 10. Artifacts & Decisions
- **Artifact Registry**: Tracks all artifacts generated in a project
- **Artifact Relationships**: Artifacts can depend on other artifacts
- **Decision History**: Project memory stores key decisions and rationale
- **Export**: Artifacts can be exported or synced via Portable Configuration

## Project / Playbook Flow: The Mental Model

The **Project / Playbook flow** is the default mental model for organizing work:

```text
Project  →  Intents  →  Playbooks  →  AI Team Execution  →  Artifacts & Decisions
```

### Concept Breakdown

#### Project = Deliverable Container
- A **Project** is a container for related work with a clear deliverable
- Examples: "Write my 2026 book", "Launch product MVP", "Content studio operations"
- **Lifecycle**: open → closed → archived
- **Ownership**: initiator, human owner, AI PM
- **Sandbox**: Each project has its own isolated file space

#### Intents = Concrete Goals
- **Intents** are specific goals within a Project
- Examples: "Define book outline", "Research competitors", "Draft fundraising page"
- Created manually or extracted from conversations
- Structured as IntentCards with metadata

#### Playbooks = Reusable Workflows
- **Playbooks** describe *how* the AI team should help
- Format: `playbook.md` (human-readable) + `playbook.json` (machine-executable)
- Define steps, AI roles, tools, and expected outputs
- Examples: `daily_planning`, `content_drafting`, `web_page_spec`

#### Playbook Flow = Multi-Playbook Orchestration
- A **Playbook Flow** defines how multiple playbooks work together
- **Nodes**: Individual playbooks in the flow
- **Edges**: Dependencies between playbooks
- **Execution Order**: Topological sorting ensures correct order
- **Checkpointing**: Can resume from any node
- **Artifact Mapping**: Artifacts flow between playbooks

#### AI Team Execution = Collaborative Work
- Multiple AI roles execute playbooks simultaneously or sequentially
- Roles: planner, writer, analyst, reviewer, etc.
- Tool calls: filesystem, APIs, vector search, etc.
- Execution trace visible in timeline

#### Artifacts & Decisions = Results
- **Artifacts**: Generated files, drafts, plans, checklists
- **Decisions**: Key choices and rationale stored in Project Memory
- **Reusability**: Artifacts can be referenced in future playbooks
- **Export**: Can be exported as Portable Configuration

## Example: "Write My 2026 Book" Project

```
Project: "Write My 2026 Book"
  ├─ Intent: "Define book outline"
  │   └─ Playbook Flow: book_planning_flow
  │       ├─ Node 1: research_market (playbook: market_research)
  │       ├─ Node 2: create_outline (playbook: outline_generator)
  │       └─ Node 3: review_outline (playbook: review_checklist)
  │
  ├─ Intent: "Write Chapter 1"
  │   └─ Playbook Flow: chapter_writing_flow
  │       ├─ Node 1: draft_chapter (playbook: chapter_draft)
  │       └─ Node 2: edit_chapter (playbook: content_editor)
  │
  └─ Sandbox: sandboxes/{workspace_id}/book/{project_id}/
      ├─ research/
      │   └─ market_analysis.md
      ├─ outline/
      │   └─ book_outline.md
      └─ chapters/
          └─ chapter_1.md
```

## Example: "OpenSEO MVP" Project

```
Project: "OpenSEO MVP"
  ├─ Intent: "Define product spec"
  │   └─ Playbook: web_page_spec
  │
  ├─ Intent: "Create hero section"
  │   └─ Playbook Flow: seo_landing_page_flow
  │       ├─ Node 1: spec (playbook: web_page_spec)
  │       ├─ Node 2: hero (playbook: web_page_hero)
  │       │   └─ Artifact Mapping: spec_doc → hero_spec
  │       └─ Node 3: sections (playbook: web_page_sections)
  │
  └─ Sandbox: sandboxes/{workspace_id}/web_page/{project_id}/
      ├─ spec/
      │   └─ product_spec.md
      ├─ hero/
      │   └─ hero_section.html
      └─ sections/
          └─ feature_sections.html
```

## Mapping: README Slogan to Architecture

| README Concept | Architecture Component | Documentation |
|---------------|------------------------|---------------|
| **AI-driven visible thinking workflow** | Signal → Intent → Project/Flow → Playbooks → Sandbox → Memory | This document |
| **Surface & Command Bus** | SurfaceDefinition + CommandBus + EventStream | [Surface & Command Bus Architecture](./surface-command-bus.md) |
| **Mind Lens** | MindLensInstance + MindLensSchema + RuntimeMindLens | [Mind Lens Architecture](./mind-lens.md) |
| **Lens Composition** | LensComposition + FusionService | [Lens Composition Architecture](./lens-composition.md) |
| **Execution Context Four-Layer Model** | Task/Policy/Lens/Assets conceptual mapping | [Execution Context Four-Layer Model](./execution-context-four-layer-model.md) |
| **Project** | Project model + ProjectManager + ProjectDetector | [Project + Flow Architecture](./project-flow/project-flow-architecture.md) |
| **Intents** | IntentCards + IntentClusters + Intent Steward | [Memory & Intent Architecture](./memory-intent-architecture.md) |
| **Playbooks** | PlaybookRunner + playbook.md + playbook.json | [Playbooks & Multi-step Workflows](./playbooks-and-workflows.md) |
| **Playbook Flow** | FlowExecutor + PlaybookFlow model | [Project + Flow Architecture](./project-flow/project-flow-architecture.md) |
| **AI Team Execution** | AI roles + tool calls + execution trace | [Playbooks & Multi-step Workflows](./playbooks-and-workflows.md) |
| **Sandbox** | ProjectSandboxManager + artifact registry | [Sandbox System Architecture](./sandbox/sandbox-system-architecture.md) |
| **Memory** | WorkspaceCoreMemory + ProjectMemory + MemberProfileMemory | [Memory & Intent Architecture](./memory-intent-architecture.md) |
| **Artifacts** | ArtifactRegistry + artifact tracking | [Project + Flow Architecture](./project-flow/project-flow-architecture.md) |

## Key Design Principles

### 1. Local-First
- All core data stored locally (SQLite)
- No cloud dependencies for core functionality
- Portable Configuration enables sync/backup without credentials

### 2. Visible Thinking
- Every step is logged and traceable
- Execution traces show AI reasoning
- Decisions and rationale stored in memory
- Timeline view provides full visibility

### 3. Project-Centric Organization
- Work organized around deliverable Projects
- Projects emerge naturally from conversations
- Each Project has its own sandbox and memory
- Projects can be archived but never deleted

### 4. Reusable Workflows
- Playbooks encode reusable workflows
- Playbook Flows orchestrate multiple playbooks
- Artifacts can be reused across projects
- Portable Configuration enables sharing

### 5. Clean Boundaries
- Port/Adapter pattern separates core from adapters
- Local/Cloud boundary clearly defined
- Workspace isolation at all levels
- Extensible through Port interfaces

### 6. Perspective-Driven Execution
- Mind Lens provides perspective/viewpoint system
- Same task can be executed with different lenses
- Lens Composition enables multi-lens scenarios
- Execution Context integrates lens values for task interpretation
- See [Execution Context Four-Layer Model](./execution-context-four-layer-model.md) for conceptual framework

### 7. Capability-aware staged model routing
- Model choice is expressed as high-level capability profiles (fast, standard, precise, tool_strict, safe_write) instead of hard-coded model names inside playbooks.
- Core phases communicate via stable JSON intermediate representations, so you can evolve models and providers without breaking workflows or control flow logic.
- **Cost governance**: Each capability profile enforces cost limits per 1k tokens (e.g., FAST: $0.002, STANDARD: $0.01, PRECISE: $0.03), and the system automatically selects cost-appropriate models based on task complexity, optimizing for both cost efficiency and success rate. Simple tasks use low-cost models (saving ~90% cost), while complex tasks use high-success-rate models for reliability.

---

## Next Steps

- **Understand Core Concepts**: [Architecture Documentation](./README.md)
- **Deep Dive into Components**: See [Reading Guide](./README.md#reading-guide)
- **Extend the System**: [For Contributors](./README.md#for-contributors)

