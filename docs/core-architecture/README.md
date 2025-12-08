# Architecture Documentation

This directory contains the complete architecture documentation for Mindscape AI, including system architecture, core concepts, and implementation guides.

## Directory Structure

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

### Project + Flow + Sandbox Architecture (v2.0)

#### [Sandbox System](./sandbox/)
System-level Sandbox architecture, unifying all AI write operations.

- [Sandbox System Architecture](./sandbox/sandbox-system-architecture.md)
- [Sandbox System Implementation Steps](./sandbox/sandbox-system-implementation-steps.md)
- [Sandbox System Summary](./sandbox/sandbox-system-summary.md)

#### [Project + Flow](./project-flow/)
Project and Playbook Flow architecture for multi-playbook collaboration.

- [Project + Flow Architecture](./project-flow/project-flow-architecture.md)
- [Project + Flow Implementation Steps](./project-flow/project-flow-implementation-steps.md)
- [Project + Flow Summary](./project-flow/project-flow-summary.md)

#### [Three.js Sandbox](./threejs/)
Three.js Hero scene Sandbox implementation planning and examples.

- [Three.js Sandbox Index](./threejs/threejs-sandbox-index.md)
- [Three.js Sandbox Implementation Plan](./threejs/threejs-sandbox-implementation-plan.md)
- [Three.js Sandbox Implementation Steps](./threejs/threejs-sandbox-implementation-steps.md)
- [Three.js Sandbox Code Examples](./threejs/threejs-sandbox-code-examples.md)
- [Three.js Sandbox Quick Start](./threejs/threejs-sandbox-quick-start.md)
- [Three.js Sandbox Summary](./threejs/threejs-sandbox-summary.md)

## Core Concepts

### Mindscape Architecture (3 Layers)

1. **Signal Layer** - Collects all signals (conversations, files, tool responses, playbook results)
2. **Intent Governance Layer** - Organizes signals into IntentCards and IntentClusters
3. **Execution & Semantic Layer** - Executes playbooks, tools, and semantic engines

### Project + Flow + Sandbox Architecture

**Project**: Deliverable-level container with its own lifecycle (open, closed, archived)

**Sandbox**: Unified file space shared across all playbooks in a project

**Playbook Flow**: Multi-playbook orchestration with dependency resolution

**Value**:
- Unified worldview (same files/specs)
- Execution order enforcement
- Deliverable-level container

### Port/Adapter Pattern

Mindscape AI uses Port interfaces to maintain clean boundaries:
- **IdentityPort**: Execution context management
- **IntentRegistryPort**: Intent resolution
- **PlaybookExecutorPort**: Playbook execution

## Reading Guide

### Quick Overview
1. [Port Architecture](./port-architecture.md) - System design patterns
2. [Memory & Intent Architecture](./memory-intent-architecture.md) - Three-layer architecture
3. [Sandbox System Summary](./sandbox/sandbox-system-summary.md)
4. [Project + Flow Summary](./project-flow/project-flow-summary.md)

### Deep Dive
1. [Port Architecture](./port-architecture.md) - Hexagonal architecture patterns
2. [Execution Context](./execution-context.md) - Context flow
3. [Local/Cloud Boundary](./local-cloud-boundary.md) - Separation principles
4. [Playbooks & Multi-step Workflows](./playbooks-and-workflows.md) - Workflow execution
5. [Sandbox System Architecture](./sandbox/sandbox-system-architecture.md)
6. [Project + Flow Architecture](./project-flow/project-flow-architecture.md)

### Getting Started
1. [Sandbox System Implementation Steps](./sandbox/sandbox-system-implementation-steps.md)
2. [Project + Flow Implementation Steps](./project-flow/project-flow-implementation-steps.md)
3. [Three.js Sandbox Quick Start](./threejs/threejs-sandbox-quick-start.md)

## Architecture Relationship

```
Workspace (long-term room, years of collaboration)
    ↓
Project (deliverable container, has its own lifecycle)
    ↓
Playbook Flow (execution flow)
    ↓
Shared Sandbox (file world)
    ↓
SandboxManager (system-level)
```

---
